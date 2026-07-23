"""Hata mesajından deterministik hata sınıfı çıkarımı.

Sınıflandırma, agent'a (opencode/Claude Code) hangi görev şablonunun
verileceğini seçer — hepsi aynı agent_cli üzerinden çalışır:

locator → agent'a DOM özeti + kırılan seçici içeren görev verilir
logic   → agent'a hata + artefakt özeti içeren görev verilir
unknown → logic ile aynı şablon (agent genel amaçlı, sınıf belirsiz olsa da dener)
infra   → agent'a gitmez, insana işaretlenir (ortam sorunu, LLM ile çözülmez;
          `mode="force"` ile zorlanabilir)
"""
from __future__ import annotations

_INFRA_MARKERS = (
    "SessionNotCreatedException",
    "UnreachableBrowserException",
    "invalid session id",
    "chrome not reachable",
    "Connection refused",
    "ERR_CONNECTION",
    "unknown error: cannot find Chrome",
    "unable to connect to renderer",
)

_LOCATOR_MARKERS = (
    "NoSuchElementException",
    "Unable to locate element",
    "no such element",
    "TimeoutException",
    "waiting for element",
    "waiting for visibility of element",
    "NodeQueryException",       # TestFX: node bulunamadı
    "no nodes matched",
)

_LOGIC_MARKERS = (
    "AssertionError",
    "AssertionFailedError",
    "ComparisonFailure",
    "expected:",
    "Expecting actual",         # AssertJ
)


def classify(error_message: str | None) -> str:
    if not error_message:
        return "unknown"
    if any(m in error_message for m in _INFRA_MARKERS):
        return "infra"
    if any(m in error_message for m in _LOCATOR_MARKERS):
        return "locator"
    if any(m in error_message for m in _LOGIC_MARKERS):
        return "logic"
    return "unknown"
