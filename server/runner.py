"""Test koşumlarının yaşam döngüsü: subprocess başlatma, canlı log yayını,
ilerleme takibi, iptal ve koşum sonu istatistik toplama."""
from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

_IS_WINDOWS = sys.platform == "win32"

from .config import ProjectConfig, ServerConfig
from .db import Database
from .parsers import collect_stats
from .progress import ProgressTracker, tail_progress

_STOP_GRACE_SECONDS = 10
_LINE_LIMIT = 1024 * 1024  # tek log satırı üst sınırı


class RunAlreadyActive(Exception):
    pass


@dataclass
class RunHandle:
    run_id: str
    project: ProjectConfig
    process: asyncio.subprocess.Process
    log_path: Path
    started_at: datetime
    started_epoch: float = 0.0
    buffer: list[str] = field(default_factory=list)          # tüm log satırları
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    progress: dict | None = None
    stop_requested: bool = False
    is_retry: bool = False
    parent_run_id: str | None = None


class RunManager:
    def __init__(self, config: ServerConfig, db: Database):
        self.config = config
        self.db = db
        self.logs_dir = Path(config.data_dir) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = Path(config.data_dir) / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.active: dict[str, RunHandle] = {}
        self._by_project: dict[str, str] = {}

    def _prune_old_runs(self, project_id: str) -> None:
        for removed in self.db.prune_runs(project_id, self.config.keep_runs):
            if removed.get("log_file"):
                Path(removed["log_file"]).unlink(missing_ok=True)
            shutil.rmtree(self.artifacts_dir / removed["id"], ignore_errors=True)

    def active_run_for(self, project_id: str) -> str | None:
        return self._by_project.get(project_id)

    async def start_run(self, project: ProjectConfig, *,
                        command_override: str | None = None,
                        is_retry: bool = False,
                        parent_run_id: str | None = None) -> str:
        if project.id in self._by_project:
            raise RunAlreadyActive(self._by_project[project.id])

        cwd = Path(project.path).resolve()
        if not cwd.is_dir():
            raise FileNotFoundError(f"Proje dizini yok: {cwd}")

        ndjson_path: Path | None = None
        if project.live_progress.cucumber_ndjson:
            # Önceki koşumdan kalan dosya canlı sayacı bozmasın.
            # (Windows'ta dosya kilitliyse silinemeyebilir — koşumu
            # engelleme; Cucumber dosyayı zaten baştan yazar.)
            ndjson_path = cwd / project.live_progress.cucumber_ndjson
            try:
                ndjson_path.unlink(missing_ok=True)
            except OSError:
                pass
        if not is_retry:
            # Önceki koşumun hata artefaktları yenisine karışmasın
            # (retry aynı koşumun devamı sayılır, dokunma)
            shutil.rmtree(cwd / project.results.failure_artifacts_dir,
                          ignore_errors=True)

        started = datetime.now()  # subprocess'ten ÖNCE: rapor mtime eşiği
        run_id = f"{project.id}-{started:%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
        log_path = self.logs_dir / f"{run_id}.log"

        # {python} → sunucuyu çalıştıran Python yorumlayıcısı. Python tabanlı
        # test komutları (örn. fake-sim) böylece platformdan bağımsız yazılır
        # (Linux'ta python3, Windows'ta python/py derdi kalmaz).
        command = ((command_override or project.command)
                   .replace("{python}", f'"{sys.executable}"'))

        # Stop'un mvn→java→chrome zincirinin tamamını öldürebilmesi için süreç
        # kendi grubunda başlar: POSIX'te setsid, Windows'ta yeni process group.
        if _IS_WINDOWS:
            group_kwargs = {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            group_kwargs = {"start_new_session": True}
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            env={**os.environ, **project.env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=_LINE_LIMIT,
            **group_kwargs,
        )

        handle = RunHandle(
            run_id=run_id, project=project, process=process,
            log_path=log_path, started_at=started,
            started_epoch=started.timestamp(),
            is_retry=is_retry, parent_run_id=parent_run_id,
        )
        self.active[run_id] = handle
        self._by_project[project.id] = run_id
        self.db.create_run(run_id, project.id, str(log_path),
                           is_retry=is_retry, parent_run_id=parent_run_id)

        asyncio.create_task(self._drive_run(handle, cwd, ndjson_path))
        return run_id

    async def stop_run(self, run_id: str) -> None:
        handle = self.active.get(run_id)
        if handle is None:
            raise KeyError(run_id)
        handle.stop_requested = True
        if _IS_WINDOWS:
            # Windows'ta güvenilir "nazik" grup sinyali yok; süreç ağacını
            # taskkill ile indir (mvn → java → chromedriver → chrome dahil).
            subprocess.run(
                ["taskkill", "/PID", str(handle.process.pid), "/T", "/F"],
                capture_output=True)
        else:
            self._signal_group(handle, signal.SIGTERM)
            asyncio.create_task(self._kill_if_alive(handle))

    def subscribe(self, run_id: str) -> tuple[list[str], dict | None, asyncio.Queue] | None:
        """Aktif koşuma abone ol: (mevcut log satırları, son ilerleme, canlı kuyruk)."""
        handle = self.active.get(run_id)
        if handle is None:
            return None
        queue: asyncio.Queue = asyncio.Queue()
        backlog = list(handle.buffer)
        handle.subscribers.add(queue)
        return backlog, handle.progress, queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        handle = self.active.get(run_id)
        if handle is not None:
            handle.subscribers.discard(queue)

    # --- iç işleyiş ---------------------------------------------------------

    async def _drive_run(self, handle: RunHandle, cwd: Path,
                         ndjson_path: Path | None) -> None:
        stop_tail = asyncio.Event()
        tail_task = None
        if ndjson_path is not None:
            tracker = ProgressTracker()

            def on_progress(snapshot: dict) -> None:
                handle.progress = snapshot
                self._broadcast(handle, snapshot)

            tail_task = asyncio.create_task(
                tail_progress(ndjson_path, tracker, on_progress, stop_tail)
            )

        try:
            with open(handle.log_path, "w", encoding="utf-8", errors="replace") as logf:
                assert handle.process.stdout is not None
                async for raw in handle.process.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    logf.write(line + "\n")
                    logf.flush()
                    handle.buffer.append(line)
                    self._broadcast(handle, {"type": "log", "line": line})
        except (ValueError, OSError) as exc:  # aşırı uzun satır vb.
            self._broadcast(handle, {"type": "log",
                                     "line": f"[runner] log okuma hatası: {exc}"})

        exit_code = await handle.process.wait()
        stop_tail.set()
        if tail_task is not None:
            await tail_task

        await self._finalize(handle, cwd, exit_code)

    async def _finalize(self, handle: RunHandle, cwd: Path, exit_code: int) -> None:
        project = handle.project
        stats = collect_stats(cwd, project.results.cucumber_json,
                              project.results.junit_xml_dir,
                              since=handle.started_epoch)
        duration_s = round((datetime.now() - handle.started_at).total_seconds(), 1)

        if handle.stop_requested:
            status = "stopped"
        elif stats is not None and stats.total > 0:
            if stats.failed > 0:
                status = "failed"
            elif exit_code == 0:
                status = "passed"
            else:
                status = "error"  # testler geçmiş görünüyor ama komut hatayla çıktı
        else:
            status = "passed" if exit_code == 0 else "error"

        if stats is not None:
            self.db.finish_run(
                handle.run_id, status, exit_code,
                passed=stats.passed, failed=stats.failed, skipped=stats.skipped,
                total=stats.total, duration_s=duration_s,
            )
            self.db.save_scenarios(handle.run_id,
                                   [s.as_dict() for s in stats.scenarios])
        else:
            self.db.finish_run(handle.run_id, status, exit_code,
                               duration_s=duration_s)

        # Retry koşumuysa: parent'ta FAIL olup şimdi geçenleri flaky işaretle
        if handle.is_retry and handle.parent_run_id and stats is not None:
            parent_failed = {s["scenario"]
                             for s in self.db.get_scenarios(handle.parent_run_id)
                             if s["status"] == "failed"}
            now_passed = {s.scenario for s in stats.scenarios
                          if s.status == "passed"}
            flaky = sorted(parent_failed & now_passed)
            if flaky:
                self.db.mark_passed_on_retry(handle.parent_run_id, flaky)

        # Hata artefaktlarını sakla (Faz 2 healing girdisi)
        if status in ("failed", "error"):
            src = cwd / project.results.failure_artifacts_dir
            if src.is_dir():
                try:
                    shutil.copytree(src, self.artifacts_dir / handle.run_id,
                                    dirs_exist_ok=True)
                except OSError:
                    pass

        # Kayıttan düş — retry başlatmadan ÖNCE (aksi halde 409)
        self.active.pop(handle.run_id, None)
        if self._by_project.get(project.id) == handle.run_id:
            self._by_project.pop(project.id, None)

        # Otomatik retry: FAIL + retry tanımlı + rerun dosyası dolu + kendisi
        # retry değil → sadece kalan senaryoları bir kez daha koş
        retry_run_id = None
        if (not handle.is_retry and status == "failed"
                and project.retry is not None and project.retry.enabled):
            rerun_path = cwd / project.retry.rerun_file
            if rerun_path.is_file() and rerun_path.read_text(
                    encoding="utf-8", errors="replace").strip():
                try:
                    retry_run_id = await self.start_run(
                        project, command_override=project.retry.command,
                        is_retry=True, parent_run_id=handle.run_id)
                except (RunAlreadyActive, FileNotFoundError):
                    pass

        finished_event = {
            "type": "finished",
            "status": status,
            "exit_code": exit_code,
            "duration_s": duration_s,
            "retry_run_id": retry_run_id,
            "stats": {
                "passed": stats.passed if stats else 0,
                "failed": stats.failed if stats else 0,
                "skipped": stats.skipped if stats else 0,
                "total": stats.total if stats else 0,
            },
        }
        self._broadcast(handle, finished_event)
        for queue in list(handle.subscribers):
            queue.put_nowait(None)  # akış bitti işareti

        self._prune_old_runs(project.id)

    def _broadcast(self, handle: RunHandle, event: dict) -> None:
        for queue in list(handle.subscribers):
            queue.put_nowait(event)

    def _signal_group(self, handle: RunHandle, sig: signal.Signals) -> None:
        try:
            os.killpg(os.getpgid(handle.process.pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    async def _kill_if_alive(self, handle: RunHandle) -> None:
        try:
            await asyncio.wait_for(handle.process.wait(), _STOP_GRACE_SECONDS)
        except asyncio.TimeoutError:
            self._signal_group(handle, signal.SIGKILL)
