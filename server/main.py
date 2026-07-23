"""FastAPI uygulaması: REST + WebSocket + statik web arayüzü.

Çalıştırma:  uvicorn server.main:app --host 0.0.0.0 --port 8000
Config yolu: CONFIG_PATH ortam değişkeni (varsayılan ./projects.yaml)
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import check_ws_token, require_token
from .config import load_config
from .db import Database
from .healing import HealError
from .healing.engine import HealBusy, HealEngine
from .runner import RunAlreadyActive, RunManager


class HealRequest(BaseModel):
    scenario: str
    mode: str = "auto"  # auto (infra sınıfını reddeder) | force (yine de dene)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(config_path: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = load_config(config_path)
        data_dir = Path(config.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        db = Database(data_dir / "runs.db")
        app.state.config = config
        app.state.db = db
        app.state.manager = RunManager(config, db)
        app.state.heal_engine = HealEngine(config, db)
        yield
        db.close()

    app = FastAPI(title="Test Runner Server", lifespan=lifespan)

    # --- REST ---------------------------------------------------------------

    @app.get("/api/projects", dependencies=[Depends(require_token)])
    def list_projects():
        manager: RunManager = app.state.manager
        result = []
        for project in app.state.config.projects:
            result.append({
                "id": project.id,
                "name": project.name,
                "path": project.path,
                "command": project.command,
                "active_run_id": manager.active_run_for(project.id),
                "last_run": app.state.db.last_run(project.id),
            })
        return result

    @app.post("/api/projects/{project_id}/run",
              dependencies=[Depends(require_token)], status_code=201)
    async def start_run(project_id: str):
        project = app.state.config.project(project_id)
        if project is None:
            raise HTTPException(404, f"Proje tanımlı değil: {project_id}")
        try:
            run_id = await app.state.manager.start_run(project)
        except RunAlreadyActive as exc:
            raise HTTPException(
                409, f"Bu projede koşum zaten aktif: {exc.args[0]}") from exc
        except FileNotFoundError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"run_id": run_id}

    @app.post("/api/runs/{run_id}/stop", dependencies=[Depends(require_token)])
    async def stop_run(run_id: str):
        try:
            await app.state.manager.stop_run(run_id)
        except KeyError:
            raise HTTPException(404, "Aktif koşum bulunamadı") from None
        return {"status": "stopping"}

    @app.get("/api/runs", dependencies=[Depends(require_token)])
    def list_runs(project: str | None = None, limit: int = 50):
        return app.state.db.list_runs(project, min(limit, 500))

    @app.get("/api/runs/{run_id}", dependencies=[Depends(require_token)])
    def get_run(run_id: str):
        run = app.state.db.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Koşum bulunamadı")
        manager: RunManager = app.state.manager
        handle = manager.active.get(run_id)
        project = app.state.config.project(run["project_id"])
        run["scenarios"] = app.state.db.get_scenarios(run_id)
        run["live_progress"] = handle.progress if handle else None
        run["retry_run_id"] = app.state.db.find_retry_run(run_id)
        run["agent_enabled"] = bool(project and project.agent)
        run["heals"] = app.state.db.list_heals(run_id=run_id)
        return run

    @app.get("/api/runs/{run_id}/log", dependencies=[Depends(require_token)])
    def get_log(run_id: str):
        run = app.state.db.get_run(run_id)
        if run is None or not run.get("log_file"):
            raise HTTPException(404, "Koşum bulunamadı")
        log_path = Path(run["log_file"])
        if not log_path.is_file():
            raise HTTPException(404, "Log dosyası yok")
        return PlainTextResponse(log_path.read_text(encoding="utf-8",
                                                    errors="replace"))

    # --- Healing (Faz 2) -------------------------------------------------------

    @app.post("/api/runs/{run_id}/heal",
              dependencies=[Depends(require_token)], status_code=201)
    async def start_heal(run_id: str, body: HealRequest):
        run = app.state.db.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Koşum bulunamadı")
        project = app.state.config.project(run["project_id"])
        if project is None or project.agent is None:
            raise HTTPException(
                400, "Bu projede `agent` yapılandırması yok (projects.yaml).")
        scenario_row = next(
            (s for s in app.state.db.get_scenarios(run_id)
             if s["scenario"] == body.scenario and s["status"] == "failed"),
            None)
        if scenario_row is None:
            raise HTTPException(
                404, f"Bu koşumda FAIL olmuş '{body.scenario}' senaryosu yok.")
        if scenario_row.get("passed_on_retry"):
            raise HTTPException(
                409, "Bu senaryo retry'da geçti (flaky şüphesi) — kod "
                     "düzeltmesi değil, kararlılık incelemesi gerekir.")
        try:
            heal_id = await app.state.heal_engine.start_heal(
                project, run, scenario_row, body.mode)
        except HealBusy:
            raise HTTPException(
                409, "Bu projede zaten aktif bir heal denemesi var.") from None
        except HealError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"heal_id": heal_id}

    @app.get("/api/heals", dependencies=[Depends(require_token)])
    def list_heals(run: str | None = None, limit: int = 50):
        return app.state.db.list_heals(run_id=run, limit=min(limit, 200))

    @app.get("/api/heals/{heal_id}", dependencies=[Depends(require_token)])
    def get_heal(heal_id: str):
        heal = app.state.db.get_heal(heal_id)
        if heal is None:
            raise HTTPException(404, "Heal denemesi bulunamadı")
        try:
            heal["stages"] = json.loads(heal.pop("detail") or "[]")
        except json.JSONDecodeError:
            heal["stages"] = []
        return heal

    @app.get("/api/heals/{heal_id}/log", dependencies=[Depends(require_token)])
    def get_heal_log(heal_id: str):
        if app.state.db.get_heal(heal_id) is None:
            raise HTTPException(404, "Heal denemesi bulunamadı")
        log_path = app.state.heal_engine.heal_log_path(heal_id)
        text = (log_path.read_text(encoding="utf-8", errors="replace")
                if log_path.is_file() else "")
        return PlainTextResponse(text)

    @app.post("/api/heals/{heal_id}/approve",
              dependencies=[Depends(require_token)])
    async def approve_heal(heal_id: str):
        return await _resolve_heal(heal_id, approve=True)

    @app.post("/api/heals/{heal_id}/reject",
              dependencies=[Depends(require_token)])
    async def reject_heal(heal_id: str):
        return await _resolve_heal(heal_id, approve=False)

    async def _resolve_heal(heal_id: str, approve: bool):
        try:
            return await asyncio.to_thread(
                app.state.heal_engine.resolve, heal_id, approve)
        except KeyError:
            raise HTTPException(404, "Heal denemesi bulunamadı") from None
        except HealError as exc:
            raise HTTPException(409, str(exc)) from exc

    # --- WebSocket: canlı log + ilerleme -------------------------------------

    @app.websocket("/api/runs/{run_id}/stream")
    async def stream_run(websocket: WebSocket, run_id: str):
        await websocket.accept()
        if not check_ws_token(websocket):
            await websocket.send_json({"type": "error", "error": "unauthorized"})
            await websocket.close(code=1008)
            return

        manager: RunManager = app.state.manager
        subscription = manager.subscribe(run_id)

        try:
            if subscription is None:
                # Koşum aktif değil: geçmişten log + sonucu gönder, kapat
                run = app.state.db.get_run(run_id)
                if run is None:
                    await websocket.send_json({"type": "error",
                                               "error": "run not found"})
                    await websocket.close(code=1008)
                    return
                log_path = Path(run.get("log_file") or "")
                lines = (log_path.read_text(encoding="utf-8", errors="replace")
                         .splitlines() if log_path.is_file() else [])
                await websocket.send_json({"type": "backlog", "lines": lines})
                await websocket.send_json({
                    "type": "finished",
                    "status": run["status"],
                    "exit_code": run["exit_code"],
                    "duration_s": run["duration_s"],
                    "stats": {k: run[k] for k in
                              ("passed", "failed", "skipped", "total")},
                })
                await websocket.close()
                return

            backlog, progress, queue = subscription
            try:
                await websocket.send_json({"type": "backlog", "lines": backlog})
                if progress:
                    await websocket.send_json(progress)
                while True:
                    event = await queue.get()
                    if event is None:  # koşum bitti
                        break
                    await websocket.send_json(event)
                await websocket.close()
            finally:
                manager.unsubscribe(run_id, queue)
        except WebSocketDisconnect:
            pass

    # Statik arayüz en sonda mount edilir ki /api önce eşleşsin
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
    return app


app = create_app()
