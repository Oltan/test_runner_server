"""Hata mesajından deterministik hata sınıfı çıkarımı.

locator → Mod A (tek çağrılık locator düzeltme)
logic   → Mod B (coding agent)
infra   → LLM'e gitmez, insana işaretlenir
unknown → otomatik yönlendirilmez; kullanıcı isterse Mod B'ye zorlayabilir
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
