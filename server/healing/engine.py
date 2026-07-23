"""Heal denemesi orkestrasyonu.

Tek akış (izole git worktree + kendi branch'inde): sınıflandır → görev
metnini hazırla (locator sınıfı için DOM özeti + kırılan seçici; diğerleri
için hata + artefakt özeti) → coding agent'ı (opencode/Claude Code) çalıştır
→ diff whitelist kontrolü → (compile) → senaryoyu yeniden koş → diff öner.

Kod düzenlemeyi agent yapar — sunucu kendi regex/JSON/literal-patch
mekanizmasıyla uğraşmaz. Bu yüzden locator kırılmaları da dahil HER hata
sınıfı aynı yoldan geçer; sınıflandırma sadece hangi prompt şablonunun
kullanılacağını seçer (ve "infra" sınıfını insan incelemesine ayırır —
tarayıcı/ortam sorunları LLM ile çözülmez).

Hiçbir agent kendi kendine push/merge yapmaz; sonuç "proposed" olarak
insan onayına sunulur (approve → branch kalır, reject → branch silinir).
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import HealError
from ..config import ProjectConfig, ServerConfig
from ..db import Database
from .agents import build_agent_argv
from .classify import classify
from .domprune import prune_dom
from .locator import extract_locator, find_occurrences
from .patch import changed_paths, whitelist_violations
from .workspace import cleanup, commit, create_worktree, stage_and_diff

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "agent" / "prompts"
_MAX_DIFF_CHARS = 200_000


class HealBusy(Exception):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _quote_for_display(arg: str) -> str:
    """argv elemanını okunabilir log satırı için tırnaklar (yeniden
    çalıştırmak için değil, sadece görüntü amaçlıdır)."""
    return shlex.quote(arg) if arg else '""'


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
        self.logs_dir = Path(config.data_dir) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._active_projects: set[str] = set()

    def heal_log_path(self, heal_id: str) -> Path:
        return self.logs_dir / f"heal-{heal_id}.log"

    def _log(self, heal_id: str, text: str) -> None:
        with open(self.heal_log_path(heal_id), "a", encoding="utf-8",
                  errors="replace") as f:
            f.write(text)

    def _stream_cmd(self, heal_id: str, command: str | list[str], cwd: Path,
                    env: dict, timeout: int) -> tuple[int, str]:
        """Komutu çalıştırır, çıktısını satır satır heal log dosyasına akıtır
        (arayüz bu dosyayı canlı gösterir). (exit_code, kuyruk) döner.

        `command` bir liste ise (agent_cli: opencode/claude-code) argv
        olarak, shell'e HİÇ girmeden çalıştırılır — tırnak/kaçış karakteri
        derdi olmaz, prompt içeriği ne olursa olsun sorunsuz geçer. Loga
        yazılan satır da terminalde elle yazacağınız komutla birebir aynıdır.
        Düz metin ise (agent_cli: custom, mvn/derleme komutları) shell
        üzerinden çalışır (pipe/redirect/env genişletme gerekebilir)."""
        display = (" ".join(_quote_for_display(c) for c in command)
                   if isinstance(command, list) else command)
        self._log(heal_id, f"\n$ {display}\n")
        proc = subprocess.Popen(command, shell=isinstance(command, str),
                                cwd=cwd, env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, errors="replace")
        timed_out = threading.Event()

        def _kill():
            timed_out.set()
            proc.kill()
        timer = threading.Timer(timeout, _kill)
        timer.start()
        tail: deque[str] = deque(maxlen=200)
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._log(heal_id, line)
                tail.append(line)
            returncode = proc.wait()
        finally:
            timer.cancel()
        if timed_out.is_set():
            raise HealError(f"Komut zaman aşımına uğradı ({timeout}s): "
                            f"{display}")
        return returncode, "".join(tail)[-1200:]

    # --- başlatma -------------------------------------------------------------

    async def start_heal(self, project: ProjectConfig, run: dict,
                         scenario_row: dict, mode: str = "auto") -> str:
        agent = project.agent
        if agent is None:
            raise HealError("Bu projede `agent` yapılandırması yok.")
        if project.id in self._active_projects:
            raise HealBusy(project.id)

        failure_class = classify(scenario_row.get("error_message"))
        force = mode.lower() == "force"
        if failure_class == "infra" and not force:
            raise HealError(
                "Hata sınıfı 'infra' — bu genelde ortam/bağlantı sorunudur "
                "(ör. tarayıcı başlatılamadı), LLM ile düzeltilemez. İnsan "
                "incelemesi gerekir. Yine de denemek isterseniz "
                "mode='force' kullanın (önerilmez).")
        if agent.agent_cli == "custom" and not agent.agent_command:
            raise HealError(
                "`agent.agent_cli` seçin (opencode/claude-code) ya da "
                "`agent_command` yazın.")

        heal_id = uuid4().hex[:12]
        self.db.create_heal(heal_id, run["id"], project.id,
                            scenario_row["scenario"], failure_class,
                            agent.agent_cli, agent.agent_model)
        self._active_projects.add(project.id)
        asyncio.create_task(self._execute(heal_id, project, run,
                                          scenario_row, failure_class))
        return heal_id

    async def _execute(self, heal_id: str, project: ProjectConfig, run: dict,
                       scenario_row: dict, failure_class: str) -> None:
        try:
            await asyncio.to_thread(self._pipeline, heal_id, project, run,
                                    scenario_row, failure_class)
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
                  scenario_row: dict, failure_class: str) -> None:
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
            self._log(heal_id, f"═══ Heal {heal_id} — senaryo: "
                               f"{scenario_row['scenario']!r}, sınıf: "
                               f"{failure_class}, agent: {agent.agent_cli} "
                               f"═══\n")
            step("worktree", lambda: self._make_worktree(
                repo_root, worktree, branch, heal_id))
            worktree_created = True

            self._fix_with_agent(step, heal_id, project, run, scenario_row,
                                 worktree, failure_class)

            if agent.compile_command:
                step("derleme", lambda: self._run_verified(
                    heal_id, agent.compile_command, worktree, project,
                    scenario_row, agent.command_timeout_s,
                    "Derleme başarısız — öneri geri çekildi"))

            step("senaryo doğrulama", lambda: self._run_verified(
                heal_id, agent.scenario_command, worktree, project,
                scenario_row, agent.command_timeout_s,
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

    # --- görev metni hazırlama --------------------------------------------------------

    def _locator_prompt(self, run: dict, scenario_row: dict,
                        worktree: Path, agent) -> str:
        """Locator sınıfı için: kırılan seçici + budanmış DOM + (varsa)
        muhtemel dosya ipucu. Hiçbiri bulunamasa da agent repoyu kendisi
        arayabilir — bunlar zorunlu değil, sadece hızlandırıcı bağlam."""
        error_message = scenario_row.get("error_message") or ""
        located = extract_locator(error_message)
        locator_line = ("(hata mesajından belirli bir seçici çıkarılamadı — "
                        "hata mesajının tamamına bakın)")
        hint_file = "(otomatik bulunamadı — repo içinde arayın)"
        dom_context = ("(DOM dump'ı bulunamadı — hata anında yakalanmamış "
                       "olabilir; sayfayı/kodu kendin incele)")

        if located:
            loc_type, loc_value = located
            locator_line = f"{loc_type}: {loc_value}"
            try:
                hits = find_occurrences(worktree, agent.edit_whitelist, loc_value)
                if hits:
                    hint_file = str(hits[0][0].relative_to(worktree))
            except OSError:
                pass

            run_artifacts = self.artifacts_dir / run["id"]
            blocks = []
            for html_file in sorted(run_artifacts.rglob("*.html"))[:4]:
                html = html_file.read_text(encoding="utf-8", errors="replace")
                pruned = prune_dom(html, loc_value)
                if pruned:
                    blocks.append(f"— {html_file.name} —\n{pruned}")
            if blocks:
                dom_context = "\n\n".join(blocks)

        template = (_PROMPTS_DIR / "fix_locator.md").read_text(encoding="utf-8")
        return _fill(template, {
            "scenario": scenario_row["scenario"],
            "error_message": error_message[:2000],
            "locator_line": locator_line,
            "hint_file": hint_file,
            "dom_context": dom_context,
            "whitelist": ", ".join(agent.edit_whitelist),
            "scenario_command": agent.scenario_command,
        })

    def _generic_prompt(self, run: dict, scenario_row: dict, agent) -> str:
        template = (_PROMPTS_DIR / "fix_generic.md").read_text(encoding="utf-8")
        return _fill(template, {
            "scenario": scenario_row["scenario"],
            "feature": scenario_row.get("feature") or "-",
            "error_message": (scenario_row.get("error_message") or "")[:3000],
            "artifacts_summary": self._artifacts_summary(run["id"]),
            "whitelist": ", ".join(agent.edit_whitelist),
            "scenario_command": agent.scenario_command,
        })

    # --- agent çalıştırma (tüm hata sınıfları için tek yol) ------------------------------

    def _fix_with_agent(self, step, heal_id: str, project: ProjectConfig,
                        run: dict, scenario_row: dict, worktree: Path,
                        failure_class: str) -> None:
        agent = project.agent
        prompt_file = worktree / "HEAL_TASK.md"

        def write_task() -> str:
            prompt = (self._locator_prompt(run, scenario_row, worktree, agent)
                     if failure_class == "locator"
                     else self._generic_prompt(run, scenario_row, agent))
            prompt_file.write_text(prompt, encoding="utf-8")
            return prompt_file.name
        step("görev dosyası", write_task)

        def run_agent() -> str:
            env = {
                **os.environ, **project.env, **agent.env,
                "HEAL_PROMPT_FILE": str(prompt_file),
                "HEAL_MODEL": agent.agent_model or "",
                "HEAL_SCENARIO": scenario_row["scenario"],
            }
            if agent.agent_command:
                # Tam kontrol: agent_command bir shell komut şablonudur.
                command = render_command(
                    agent.agent_command, prompt_file=str(prompt_file),
                    model=agent.agent_model or "",
                    scenario=scenario_row["scenario"],
                    python=f'"{sys.executable}"')
            else:
                # Hazır CLI: gerçek argv — terminalde elle yazacağınız
                # komutla birebir aynı; shell'e hiç girmez (tırnak/kaçış
                # karakteri derdi yok), log'da da bu haliyle görünür.
                command = build_agent_argv(
                    agent.agent_cli,
                    prompt_file.read_text(encoding="utf-8"),
                    model=agent.agent_model or "",
                    binary=agent.env.get("HEAL_AGENT_BIN", ""),
                    extra_args=agent.env.get("HEAL_AGENT_ARGS", "").split(),
                    allowed_tools=agent.env.get("HEAL_ALLOWED_TOOLS", ""))
            returncode, tail = self._stream_cmd(
                heal_id, command, worktree, env, agent.command_timeout_s)
            if returncode != 0:
                raise HealError(f"Agent hatayla çıktı "
                                f"(exit {returncode}): {tail[-600:]}")
            return tail[-600:]
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

    def _run_verified(self, heal_id: str, command: str, worktree: Path,
                      project: ProjectConfig, scenario_row: dict,
                      timeout: int, fail_message: str) -> str:
        env = {**os.environ, **project.env,
               "HEAL_SCENARIO": scenario_row["scenario"]}
        command = render_command(command, scenario=scenario_row["scenario"],
                                 python=f'"{sys.executable}"')
        returncode, tail = self._stream_cmd(heal_id, command, worktree,
                                            env, timeout)
        if returncode != 0:
            raise HealError(f"{fail_message} (exit {returncode}): "
                            f"{tail[-600:]}")
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
