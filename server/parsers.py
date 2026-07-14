"""Koşum sonu rapor parser'ları: Cucumber JSON ve JUnit (surefire) XML.

Her ikisi de RunStats üretir; runner koşum bitince önce cucumber_json'ı,
yoksa junit_xml_dir'i dener.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_NS = 1_000_000_000  # Cucumber JSON süreleri nanosaniye


@dataclass
class ScenarioResult:
    scenario: str
    status: str  # passed|failed|skipped
    feature: str | None = None
    duration_s: float | None = None
    error_message: str | None = None

    def as_dict(self) -> dict:
        return {
            "feature": self.feature,
            "scenario": self.scenario,
            "status": self.status,
            "duration_s": self.duration_s,
            "error_message": self.error_message,
        }


@dataclass
class RunStats:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_s: float | None = None
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped


def _scenario_status(steps: list[dict]) -> tuple[str, str | None]:
    """Adım sonuçlarından senaryo durumu: herhangi biri geçmediyse failed;
    tümü passed ise passed; skipped içeriyorsa skipped."""
    saw_skipped = False
    for step in steps:
        result = step.get("result") or {}
        status = result.get("status", "skipped")
        if status == "passed":
            continue
        if status == "skipped":
            saw_skipped = True
            continue
        # failed / undefined / pending / ambiguous → hata
        return "failed", result.get("error_message")
    return ("skipped" if saw_skipped else "passed"), None


def parse_cucumber_json(path: str | Path) -> RunStats:
    with open(path, encoding="utf-8") as f:
        features = json.load(f)

    stats = RunStats()
    total_ns = 0
    for feature in features or []:
        feature_name = feature.get("name") or feature.get("uri")
        for element in feature.get("elements", []):
            if element.get("type") == "background":
                continue
            # before/after hook hataları da senaryoyu düşürür
            steps = (
                element.get("before", [])
                + element.get("steps", [])
                + element.get("after", [])
            )
            status, error = _scenario_status(steps)
            duration_ns = sum(
                (s.get("result") or {}).get("duration", 0) for s in steps
            )
            total_ns += duration_ns
            stats.scenarios.append(ScenarioResult(
                scenario=element.get("name") or "(adsız senaryo)",
                status=status,
                feature=feature_name,
                duration_s=round(duration_ns / _NS, 3),
                error_message=error,
            ))
            setattr(stats, status, getattr(stats, status) + 1)
    stats.duration_s = round(total_ns / _NS, 3)
    return stats


def parse_junit_xml_dir(path: str | Path, since: float | None = None) -> RunStats:
    stats = RunStats()
    total_time = 0.0
    for xml_file in sorted(Path(path).glob("*.xml")):
        if since is not None and xml_file.stat().st_mtime < since:
            continue  # önceki koşumdan kalan bayat rapor
        try:
            root = ET.parse(xml_file).getroot()
        except ET.ParseError:
            continue
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for suite in suites:
            total_time += float(suite.get("time", 0) or 0)
            for case in suite.findall("testcase"):
                failure = case.find("failure")
                error = case.find("error")
                if failure is not None or error is not None:
                    node = failure if failure is not None else error
                    status = "failed"
                    message = (node.get("message") or (node.text or "").strip()[:2000]
                               or None)
                elif case.find("skipped") is not None:
                    status, message = "skipped", None
                else:
                    status, message = "passed", None
                stats.scenarios.append(ScenarioResult(
                    scenario=case.get("name") or "(adsız test)",
                    status=status,
                    feature=case.get("classname"),
                    duration_s=float(case.get("time", 0) or 0),
                    error_message=message,
                ))
                setattr(stats, status, getattr(stats, status) + 1)
    stats.duration_s = round(total_time, 3)
    return stats


def collect_stats(project_dir: Path, cucumber_json: str | None,
                  junit_xml_dir: str | None,
                  since: float | None = None) -> RunStats | None:
    """Önce cucumber JSON (senaryo bazlı, hata mesajlı), yoksa JUnit XML.

    `since` verilirse (koşum başlangıcı, epoch) ondan eski rapor dosyaları
    yok sayılır — durdurulan/yarıda kesilen koşumlara önceki koşumun bayat
    raporu mal edilmesin.
    """
    if cucumber_json:
        p = project_dir / cucumber_json
        if p.is_file() and (since is None or p.stat().st_mtime >= since):
            try:
                return parse_cucumber_json(p)
            except (json.JSONDecodeError, OSError):
                pass
    if junit_xml_dir:
        p = project_dir / junit_xml_dir
        if p.is_dir():
            stats = parse_junit_xml_dir(p, since=since)
            if stats.total > 0:
                return stats
    return None
