"""SQLite koşum geçmişi: runs + scenario_results."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,              -- running|passed|failed|error|stopped
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    duration_s REAL,
    log_file TEXT,
    is_retry INTEGER NOT NULL DEFAULT 0,
    parent_run_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, started_at DESC);

CREATE TABLE IF NOT EXISTS scenario_results (
    run_id TEXT NOT NULL,
    feature TEXT,
    scenario TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_s REAL,
    error_message TEXT,
    passed_on_retry INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scen_run ON scenario_results(run_id);

CREATE TABLE IF NOT EXISTS heal_attempts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    failure_class TEXT,
    mode TEXT,                         -- a|b
    model TEXT,
    status TEXT NOT NULL,              -- running|proposed|needs_human|approved|rejected|failed
    branch TEXT,
    worktree TEXT,
    diff TEXT,
    detail TEXT,                       -- JSON: aşama kayıtları
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_heal_run ON heal_attempts(run_id);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- runs -------------------------------------------------------------

    def create_run(self, run_id: str, project_id: str, log_file: str,
                   is_retry: bool = False,
                   parent_run_id: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (id, project_id, status, started_at, log_file,"
                " is_retry, parent_run_id) VALUES (?, ?, 'running', ?, ?, ?, ?)",
                (run_id, project_id, _utcnow(), log_file,
                 int(is_retry), parent_run_id),
            )
            self._conn.commit()

    def finish_run(
        self,
        run_id: str,
        status: str,
        exit_code: int | None,
        passed: int = 0,
        failed: int = 0,
        skipped: int = 0,
        total: int = 0,
        duration_s: float | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status=?, finished_at=?, exit_code=?,"
                " passed=?, failed=?, skipped=?, total=?, duration_s=? WHERE id=?",
                (status, _utcnow(), exit_code, passed, failed, skipped, total,
                 duration_s, run_id),
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_runs(self, project_id: str | None = None, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM runs"
        params: tuple = ()
        if project_id:
            query += " WHERE project_id=?"
            params = (project_id,)
        query += " ORDER BY started_at DESC, id DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, params + (limit,)).fetchall()
        return [dict(r) for r in rows]

    def last_run(self, project_id: str) -> dict | None:
        runs = self.list_runs(project_id, limit=1)
        return runs[0] if runs else None

    # --- scenario_results ---------------------------------------------------

    def save_scenarios(self, run_id: str, scenarios: list[dict]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT INTO scenario_results"
                " (run_id, feature, scenario, status, duration_s, error_message)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (run_id, s.get("feature"), s["scenario"], s["status"],
                     s.get("duration_s"), s.get("error_message"))
                    for s in scenarios
                ],
            )
            self._conn.commit()

    def get_scenarios(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT feature, scenario, status, duration_s, error_message,"
                " passed_on_retry FROM scenario_results WHERE run_id=?",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_passed_on_retry(self, run_id: str, scenarios: list[str]) -> None:
        """Retry koşumunda geçen senaryoları parent koşumda flaky işaretle."""
        with self._lock:
            self._conn.executemany(
                "UPDATE scenario_results SET passed_on_retry=1"
                " WHERE run_id=? AND scenario=?",
                [(run_id, s) for s in scenarios],
            )
            self._conn.commit()

    def find_retry_run(self, parent_run_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM runs WHERE parent_run_id=? ORDER BY started_at"
                " DESC LIMIT 1", (parent_run_id,)
            ).fetchone()
        return row["id"] if row else None

    def prune_runs(self, project_id: str, keep: int) -> list[dict]:
        """Proje başına en yeni `keep` koşumu tut; silinenlerin id+log_file'ını
        döndür (çağıran, log ve artefakt dosyalarını temizler)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, log_file FROM runs WHERE project_id=? AND"
                " status != 'running' ORDER BY started_at DESC, id DESC"
                " LIMIT -1 OFFSET ?", (project_id, keep)
            ).fetchall()
            removed = [dict(r) for r in rows]
            if removed:
                ids = [r["id"] for r in removed]
                marks = ",".join("?" * len(ids))
                self._conn.execute(
                    f"DELETE FROM scenario_results WHERE run_id IN ({marks})", ids)
                self._conn.execute(
                    f"DELETE FROM runs WHERE id IN ({marks})", ids)
                self._conn.commit()
        return removed

    # --- heal_attempts --------------------------------------------------------

    def create_heal(self, heal_id: str, run_id: str, project_id: str,
                    scenario: str, failure_class: str, mode: str,
                    model: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO heal_attempts (id, run_id, project_id, scenario,"
                " failure_class, mode, model, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)",
                (heal_id, run_id, project_id, scenario, failure_class,
                 mode, model, _utcnow()),
            )
            self._conn.commit()

    def update_heal(self, heal_id: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE heal_attempts SET {cols} WHERE id=?",
                (*fields.values(), heal_id),
            )
            self._conn.commit()

    def get_heal(self, heal_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM heal_attempts WHERE id=?", (heal_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_heals(self, run_id: str | None = None, limit: int = 50) -> list[dict]:
        query = ("SELECT id, run_id, project_id, scenario, failure_class, mode,"
                 " model, status, branch, created_at, finished_at FROM heal_attempts")
        params: tuple = ()
        if run_id:
            query += " WHERE run_id=?"
            params = (run_id,)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, params + (limit,)).fetchall()
        return [dict(r) for r in rows]
