"""Cucumber "message" plugin'inin yazdığı NDJSON dosyasından canlı ilerleme.

Cucumber koşum başında her senaryo için bir `pickle` mesajı yazar (toplam sayı),
koşum sırasında `testStepFinished` / `testCaseFinished` mesajlarıyla adım ve
senaryo sonuçları gelir. Dosyayı tail edip anlık geçen/kalan sayısını çıkarırız.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Awaitable, Callable

# Adım durum önceliği: senaryonun durumu, adımlarının en kötüsüdür.
_SEVERITY = {
    "PASSED": 0, "SKIPPED": 1, "PENDING": 2,
    "UNDEFINED": 3, "AMBIGUOUS": 4, "FAILED": 5,
}


class ProgressTracker:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._case_status: dict[str, str] = {}

    @property
    def done(self) -> int:
        return self.passed + self.failed + self.skipped

    def snapshot(self) -> dict:
        percent = round(self.done / self.total * 100, 1) if self.total else 0.0
        return {
            "type": "progress",
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "done": self.done,
            "total": self.total,
            "percent": percent,
        }

    def feed_line(self, line: str) -> bool:
        """Bir NDJSON satırı işle; sayaçlar değiştiyse True döner."""
        line = line.strip()
        if not line:
            return False
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return False

        if "pickle" in msg:
            self.total += 1
            return True

        if "testCaseStarted" in msg:
            case_id = msg["testCaseStarted"].get("id")
            if case_id:
                self._case_status[case_id] = "PASSED"
            return False

        if "testStepFinished" in msg:
            body = msg["testStepFinished"]
            case_id = body.get("testCaseStartedId")
            status = (body.get("testStepResult") or {}).get("status", "PASSED")
            if case_id in self._case_status:
                current = self._case_status[case_id]
                if _SEVERITY.get(status, 0) > _SEVERITY.get(current, 0):
                    self._case_status[case_id] = status
            return False

        if "testCaseFinished" in msg:
            body = msg["testCaseFinished"]
            case_id = body.get("testCaseStartedId")
            status = self._case_status.pop(case_id, "PASSED")
            if body.get("willBeRetried"):
                return False  # aynı senaryo tekrar koşulacak, sayma
            if status == "PASSED":
                self.passed += 1
            elif status == "SKIPPED":
                self.skipped += 1
            else:
                self.failed += 1
            return True

        return False


async def tail_progress(
    path: Path,
    tracker: ProgressTracker,
    on_update: Callable[[dict], Awaitable[None] | None],
    stop: asyncio.Event,
    poll_interval: float = 0.3,
) -> None:
    """`path` dosyasını koşum bitene dek tail eder; sayaç değişiminde
    on_update(tracker.snapshot()) çağırır. Dosya henüz yoksa bekler."""
    offset = 0
    remainder = ""

    async def drain() -> None:
        nonlocal offset, remainder
        if not path.is_file():
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                chunk = f.read()
                offset = f.tell()
        except OSError:
            return
        if not chunk:
            return
        lines = (remainder + chunk).split("\n")
        remainder = lines.pop()  # son parça yarım satır olabilir
        changed = False
        for line in lines:
            changed = tracker.feed_line(line) or changed
        if changed:
            result = on_update(tracker.snapshot())
            if asyncio.iscoroutine(result):
                await result

    while not stop.is_set():
        await drain()
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            pass
    await drain()  # koşum bittikten sonra kalan satırlar
