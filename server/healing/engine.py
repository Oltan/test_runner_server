"""Heal denemesi orkestrasyonu.

Akış (her ikisi de izole git worktree + kendi branch'inde):
  Mod A: locator çıkar → PO dosyasını bul → DOM buda → tek LLM çağrısı →
         deterministik patch → (compile) → senaryoyu yeniden koş → diff öner
  Mod B: görev dosyası yaz → coding agent'ı çalıştır → diff whitelist
         kontrolü → (compile) → senaryoyu yeniden koş → diff öner

Hiçbir mod kendi kendine push/merge yapmaz; sonuç "proposed" olarak insan
onayına sunulur (approve → branch kalır, reject → branch silinir).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import HealError
from ..config import ProjectConfig, ServerConfig
from ..db import Database
from .classify import classify
from .domprune import prune_dom
from .llm import chat_completion, extract_json_block
from .locator import code_excerpt, extract_locator, find_occurrences
from .patch import apply_single_literal_patch, changed_paths, whitelist_violations
from .workspace import cleanup, commit, create_worktree, stage_and_diff

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "agent" / "prompts"
_MAX_DIFF_CHARS = 200_000


class HealBusy(Exception):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fill(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def render_command(template: str, **values: str) -> str:
    """Komut şablonundaki {scenario}, {prompt_file}, {model} yer tutucularını
    doldurur. Ortam değişkenlerinden (HEAL_*) farklı olarak shell'den
    bağımsızdır — aynı projects.yaml Linux'ta da Windows'ta da çalışır."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


class HealEngine:
    def __init__(self, config: ServerConfig, db: Database):
        self.config = config
        self.db = db
        self.artifacts_dir = Path(config.data_dir) / "artifacts"
        self.worktrees_dir = Path(config.data_dir) / "worktrees"
        self._active_projects: set[str] = set()

    # --- başlatma -------------------------------------------------------------

    async def start_heal(self, project: ProjectConfig, run: dict,
                         scenario_row: dict, mode: str = "auto") -> str:
        agent = project.agent
        if agent is None:
            raise HealError("Bu projede `agent` yapılandırması yok.")
        if project.id in self._active_projects:
            raise HealBusy(project.id)

        failure_class = classify(scenario_row.get("error_message"))
        mode = mode.lower()
        if mode == "auto":
            if failure_class == "locator":
                mode = "a"
            elif failure_class == "logic":
                mode = "b"
            else:
                raise HealError(
                    f"Hata sınıfı '{failure_class}' otomatik düzeltmeye uygun "
                    "değil (infra/unknown → insan incelemesi). İsterseniz "
                    "mode='b' ile agent'a zorlayabilirsiniz.")
        if mode == "a" and agent.llm is None:
            raise HealError("Mod A için `agent.llm` yapılandırması gerekli.")
        if mode == "b" and not agent.agent_command:
            raise HealError("Mod B için `agent.agent_command` gerekli.")

        heal_id = uuid4().hex[:12]
        model = (agent.llm.model if mode == "a" and agent.llm
                 else agent.agent_model)
        self.db.create_heal(heal_id, run["id"], project.id,
                            scenario_row["scenario"], failure_class, mode, model)
        self._active_projects.add(project.id)
        asyncio.create_task(self._execute(heal_id, project, run,
                                          scenario_row, mode))
        return heal_id

    async def _execute(self, heal_id: str, project: ProjectConfig, run: dict,
                       scenario_row: dict, mode: str) -> None:
        try:
            await asyncio.to_thread(self._pipeline, heal_id, project, run,
                                    scenario_row, mode)
        finally:
            self._active_projects.discard(project.id)

    # --- onay/red ---------------------------------------------------------------

    def resolve(self, heal_id: str, approve: bool) -> dict:
        heal = self.db.get_heal(heal_id)
        if heal is None:
            raise KeyError(heal_id)
        if approve and heal["status"] != "proposed":
            raise HealError(f"Sadece 'proposed' heal onaylanabilir "
                            f"(şu an: {heal['status']}).")
        if heal["status"] in ("approved", "rejected"):
            raise HealError(f"Heal zaten sonuçlanmış: {heal['status']}")
        project = self.config.project(heal["project_id"])
        if project is not None and heal.get("worktree"):
            cleanup(Path(project.path).resolve(), Path(heal["worktree"]),
                    heal["branch"], keep_branch=approve)
        status = "approved" if approve else "rejected"
        self.db.update_heal(heal_id, status=status, finished_at=_utcnow())
        return {"status": status, "branch": heal["branch"] if approve else None}

    # --- pipeline (worker thread'de koşar) ----------------------------------------

    def _pipeline(self, heal_id: str, project: ProjectConfig, run: dict,
                  scenario_row: dict, mode: str) -> None:
        agent = project.agent
        assert agent is not None
        stages: list[dict] = []
        worktree = self.worktrees_dir / heal_id
        branch = f"heal/{heal_id}"
        repo_root = Path(project.path).resolve()
        worktree_created = False

        def record(stage: str, ok: bool, detail: str = "") -> None:
            stages.append({"stage": stage, "ok": ok,
                           "detail": str(detail)[:2000]})
            self.db.update_heal(
                heal_id, detail=json.dumps(stages, ensure_ascii=False))

        def step(name: str, fn):
            try:
                result = fn()
                record(name, True, result if isinstance(result, str) else "")
                return result
            except HealError as exc:
                record(name, False, str(exc))
                raise

        try:
            step("worktree", lambda: self._make_worktree(
                repo_root, worktree, branch, heal_id))
            worktree_created = True

            if mode == "a":
                self._mod_a(step, heal_id, project, run, scenario_row, worktree)
            else:
                self._mod_b(step, heal_id, project, run, scenario_row, worktree)

            if agent.compile_command:
                step("derleme", lambda: self._run_verified(
                    agent.compile_command, worktree, project, scenario_row,
                    agent.command_timeout_s,
                    "Derleme başarısız — öneri geri çekildi"))

            step("senaryo doğrulama", lambda: self._run_verified(
                agent.scenario_command, worktree, project, scenario_row,
                agent.command_timeout_s,
                "Düzeltme sonrası senaryo hâlâ FAIL — öneri geri çekildi"))

            def finalize() -> str:
                diff = stage_and_diff(worktree)
                if not diff.strip():
                    raise HealError("Değişiklik yok — önerilecek diff üretilemedi.")
                commit(worktree, f"heal({scenario_row['scenario']}): "
                                 f"otomatik düzeltme önerisi [{heal_id}]")
                self.db.update_heal(heal_id, diff=diff[:_MAX_DIFF_CHARS])
                return f"{len(diff.splitlines())} satır diff hazır"
            step("diff + commit", finalize)

            self.db.update_heal(heal_id, status="proposed",
                                finished_at=_utcnow())
        except HealError as exc:
            status = ("needs_human"
                      if "insan onayı" in str(exc) or "insan incelemesi" in str(exc)
                      else "failed")
            self._fail(heal_id, repo_root, worktree, branch,
                       worktree_created, status)
        except Exception as exc:  # beklenmeyen — kaydet ve temizle
            record("beklenmeyen hata", False, repr(exc))
            self._fail(heal_id, repo_root, worktree, branch,
                       worktree_created, "failed")

    def _fail(self, heal_id: str, repo_root: Path, worktree: Path,
              branch: str, worktree_created: bool, status: str) -> None:
        if worktree_created:
            try:
                cleanup(repo_root, worktree, branch, keep_branch=False)
            except Exception:
                pass
        self.db.update_heal(heal_id, status=status, finished_at=_utcnow())

    def _make_worktree(self, repo_root: Path, worktree: Path,
                       branch: str, heal_id: str) -> str:
        create_worktree(repo_root, worktree, branch)
        self.db.update_heal(heal_id, branch=branch, worktree=str(worktree))
        return f"branch {branch}"

    # --- Mod A -------------------------------------------------------------------

    def _mod_a(self, step, heal_id: str, project: ProjectConfig, run: dict,
               scenario_row: dict, worktree: Path) -> None:
        agent = project.agent
        error_message = scenario_row.get("error_message") or ""
        ctx: dict = {}  # aşamalar arası taşınan değerler (thread-yerel)

        def do_extract() -> str:
            located = extract_locator(error_message)
            if located is None:
                raise HealError("Hata mesajından locator çıkarılamadı: "
                                + error_message[:200])
            ctx["loc_type"], ctx["loc_value"] = located
            return f"{located[0]}: {located[1]}"
        step("locator çıkarımı", do_extract)
        loc_type, loc_value = ctx["loc_type"], ctx["loc_value"]

        def find_code() -> str:
            hits = find_occurrences(worktree, agent.edit_whitelist, loc_value)
            if not hits:
                raise HealError(
                    f"Locator kod içinde bulunamadı: {loc_value!r} "
                    f"(dizinler: {agent.edit_whitelist})")
            ctx["target_file"] = hits[0][0]
            return f"{hits[0][0].relative_to(worktree)} (+{len(hits) - 1} dosya)"
        step("kod eşleşmesi", find_code)
        target_file = ctx["target_file"]

        def build_candidates() -> str:
            run_artifacts = self.artifacts_dir / run["id"]
            html_files = sorted(run_artifacts.rglob("*.html"))[:4]
            if not html_files:
                raise HealError(
                    f"Hata artefaktı bulunamadı ({run_artifacts}) — test "
                    "projesinde FailureArtifactHook kurulu mu?")
            blocks = []
            for html_file in html_files:
                html = html_file.read_text(encoding="utf-8", errors="replace")
                pruned = prune_dom(html, loc_value)
                if pruned:
                    blocks.append(f"— {html_file.name} —\n{pruned}")
            if not blocks:
                raise HealError("DOM dump'larından aday element çıkarılamadı.")
            return "\n\n".join(blocks)
        candidates = step("DOM budama", build_candidates)

        def call_llm() -> str:
            template = (_PROMPTS_DIR / "fix_locator.md").read_text(
                encoding="utf-8")
            prompt = _fill(template, {
                "scenario": scenario_row["scenario"],
                "error_message": error_message[:1500],
                "locator_type": loc_type,
                "locator_value": loc_value,
                "candidates": candidates,
                "file": str(target_file.relative_to(worktree)),
                "code_excerpt": code_excerpt(target_file, loc_value),
            })
            content = chat_completion(agent.llm.base_url, agent.llm.model,
                                      prompt, agent.llm.api_key_env)
            answer = extract_json_block(content)
            selector = str(answer.get("selector", "")).strip()
            selector_type = str(answer.get("selector_type", "")).strip()
            if not selector:
                raise HealError(f"LLM boş seçici döndürdü: {content[:200]}")
            if selector == loc_value:
                raise HealError("LLM aynı (kırık) seçiciyi döndürdü.")
            if selector_type and selector_type != loc_type:
                raise HealError(
                    f"LLM farklı seçici türü döndürdü ({selector_type}, "
                    f"beklenen {loc_type}) — otomatik patch güvenli değil, "
                    "insan onayı gerekir.")
            ctx["new_selector"] = selector
            return f"yeni seçici: {selector}"
        step("LLM önerisi", call_llm)

        step("patch", lambda: str(apply_single_literal_patch(
            worktree, agent.edit_whitelist, loc_value,
            ctx["new_selector"]).relative_to(worktree)))

    # --- Mod B --------------------------------------------------------------------

    def _mod_b(self, step, heal_id: str, project: ProjectConfig, run: dict,
               scenario_row: dict, worktree: Path) -> None:
        agent = project.agent
        prompt_file = worktree / "HEAL_TASK.md"

        def write_task() -> str:
            template = (_PROMPTS_DIR / "fix_assertion.md").read_text(
                encoding="utf-8")
            prompt_file.write_text(_fill(template, {
                "scenario": scenario_row["scenario"],
                "feature": scenario_row.get("feature") or "-",
                "error_message": (scenario_row.get("error_message") or "")[:3000],
                "artifacts_summary": self._artifacts_summary(run["id"]),
                "whitelist": ", ".join(agent.edit_whitelist),
                "scenario_command": agent.scenario_command,
            }), encoding="utf-8")
            return prompt_file.name
        step("görev dosyası", write_task)

        def run_agent() -> str:
            env = {
                **os.environ, **project.env,
                "HEAL_PROMPT_FILE": str(prompt_file),
                "HEAL_MODEL": agent.agent_model or "",
                "HEAL_SCENARIO": scenario_row["scenario"],
            }
            command = render_command(agent.agent_command,
                                     prompt_file=str(prompt_file),
                                     model=agent.agent_model or "",
                                     scenario=scenario_row["scenario"],
                                     python=f'"{sys.executable}"')
            try:
                result = subprocess.run(
                    command, shell=True, cwd=worktree, env=env,
                    capture_output=True, text=True,
                    timeout=agent.command_timeout_s)
            except subprocess.TimeoutExpired as exc:
                raise HealError(f"Agent zaman aşımına uğradı "
                                f"({agent.command_timeout_s}s)") from exc
            tail = ((result.stdout or "") + (result.stderr or ""))[-1200:]
            if result.returncode != 0:
                raise HealError(f"Agent hatayla çıktı "
                                f"(exit {result.returncode}): {tail}")
            return tail
        step("agent koşumu", run_agent)
        prompt_file.unlink(missing_ok=True)

        def enforce_whitelist() -> str:
            violations = whitelist_violations(worktree, agent.edit_whitelist)
            if violations:
                raise HealError(
                    "Agent whitelist DIŞINA dokundu, öneri reddedildi: "
                    + ", ".join(violations[:10]))
            changed = changed_paths(worktree)
            if not changed:
                raise HealError("Agent hiçbir değişiklik yapmadı.")
            return f"{len(changed)} dosya değişti (hepsi whitelist içinde)"
        step("whitelist kontrolü", enforce_whitelist)

    # --- ortak yardımcılar -----------------------------------------------------------

    def _run_verified(self, command: str, worktree: Path,
                      project: ProjectConfig, scenario_row: dict,
                      timeout: int, fail_message: str) -> str:
        env = {**os.environ, **project.env,
               "HEAL_SCENARIO": scenario_row["scenario"]}
        command = render_command(command, scenario=scenario_row["scenario"],
                                 python=f'"{sys.executable}"')
        try:
            result = subprocess.run(command, shell=True, cwd=worktree, env=env,
                                    capture_output=True, text=True,
                                    timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise HealError(f"{fail_message} (zaman aşımı)") from exc
        if result.returncode != 0:
            tail = ((result.stdout or "") + (result.stderr or ""))[-1200:]
            raise HealError(f"{fail_message} (exit {result.returncode}): {tail}")
        return "geçti"

    def _artifacts_summary(self, run_id: str) -> str:
        base = self.artifacts_dir / run_id
        if not base.is_dir():
            return "(artefakt yok)"
        lines = []
        for path in sorted(base.rglob("*"))[:40]:
            if path.is_file():
                rel = path.relative_to(base)
                lines.append(f"- {rel} ({path.stat().st_size} B)")
                if path.name in ("meta.json", "context.json"):
                    try:
                        lines.append("  " + path.read_text(
                            encoding="utf-8", errors="replace")[:600])
                    except OSError:
                        pass
        lines.append(f"(tam yol: {base})")
        return "\n".join(lines)
