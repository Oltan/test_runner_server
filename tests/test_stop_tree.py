"""Platforma özel süreç yönetiminin GERÇEK testi.

Bu test, koşum başlatma ve durdurmanın platforma özel yollarını çalıştığı
işletim sisteminde uçtan uca doğrular:
  - Linux/macOS: process group + SIGTERM (killpg)
  - Windows:     CREATE_NEW_PROCESS_GROUP + taskkill /T /F

Senaryo: "test komutu" bir ÇOCUK süreç başlatır (gerçekte mvn'nin java'yı,
java'nın chrome'u başlatması gibi). Durdur çağrısından sonra sadece parent
değil, ÇOCUK sürecin de öldüğü doğrulanır — heartbeat dosyaları üzerinden
(süreç canlıysa dosyaya yazmaya devam eder).

Windows'ta çalıştırmak için:
    python -m pytest tests/test_stop_tree.py -v
"""
import asyncio
import sys
import time
from pathlib import Path

import pytest

from server.config import ProjectConfig, ServerConfig
from server.db import Database
from server.runner import RunManager

_CHILD = """\
import time
from pathlib import Path
while True:
    Path("child_hb.txt").write_text(str(time.time()))
    time.sleep(0.2)
"""

_PARENT = """\
import subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable, "child.py"])
while True:
    Path("parent_hb.txt").write_text(str(time.time()))
    time.sleep(0.2)
"""


def test_stop_kills_whole_process_tree(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "child.py").write_text(_CHILD, encoding="utf-8")
    (proj / "parent.py").write_text(_PARENT, encoding="utf-8")

    project = ProjectConfig(
        id="agac", name="Süreç ağacı testi", path=str(proj),
        command=f'"{sys.executable}" parent.py')
    config = ServerConfig(auth_token="t", data_dir=str(tmp_path / "data"),
                          projects=[project])
    db = Database(Path(config.data_dir) / "runs.db")
    manager = RunManager(config, db)

    async def start_stop() -> dict:
        run_id = await manager.start_run(project)

        # parent VE child heartbeat üretmeye başlasın
        for _ in range(60):
            if ((proj / "parent_hb.txt").exists()
                    and (proj / "child_hb.txt").exists()):
                break
            await asyncio.sleep(0.25)
        else:
            pytest.fail("süreçler heartbeat üretmeye başlamadı")

        await manager.stop_run(run_id)

        for _ in range(80):  # finalize'ı bekle (POSIX grace dahil)
            run = db.get_run(run_id)
            if run["status"] != "running":
                return run
            await asyncio.sleep(0.25)
        pytest.fail("koşum 'running'den çıkmadı")

    run = asyncio.run(start_stop())
    assert run["status"] == "stopped"

    # Süreç AĞACININ tamamı öldü mü? Canlı süreç heartbeat yazmaya devam
    # ederdi — mtime'lar sabitlenmiş olmalı.
    time.sleep(0.8)
    snapshot = {name: (proj / name).stat().st_mtime
                for name in ("parent_hb.txt", "child_hb.txt")}
    time.sleep(1.5)
    for name, mtime in snapshot.items():
        assert (proj / name).stat().st_mtime == mtime, (
            f"{name} hâlâ yazılıyor — süreç ağacı tam ölmedi "
            f"(platform: {sys.platform})")

    db.close()
