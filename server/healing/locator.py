"""Selenium hata mesajından kırılan locator'ı çıkarma ve kodda arama.

Buradaki bulgular agent'a (opencode/Claude Code) verilecek prompt'u
zenginleştirmek için kullanılır — best-effort bir ipucudur, agent'ın
gerçek düzenlemeyi yapmasına engel/şart değildir. Bulunamazsa agent
repoyu kendisi arar."""
from __future__ import annotations

import re
from pathlib import Path

# Selenium 4 JSON biçimi:
#   Unable to locate element: {"method":"xpath","selector":"//button[@id='x']"}
_JSON_RE = re.compile(
    r'\{"method"\s*:\s*"([^"]+)"\s*,\s*"selector"\s*:\s*"((?:[^"\\]|\\.)*)"\}')

# By.toString biçimi:  By.xpath: //button[@id='x']
_BY_RE = re.compile(
    r"By\.(xpath|cssSelector|css|id|name|className|tagName|linkText"
    r"|partialLinkText)\s*:\s*(.+?)\s*(?:\(tried.*)?$",
    re.MULTILINE)

_METHOD_NORMALIZE = {
    "css selector": "css", "cssSelector": "css", "css": "css",
    "xpath": "xpath", "id": "id", "name": "name",
    "link text": "linkText", "linkText": "linkText",
    "partial link text": "partialLinkText", "partialLinkText": "partialLinkText",
    "tag name": "tagName", "tagName": "tagName",
    "class name": "className", "className": "className",
}


def extract_locator(error_message: str) -> tuple[str, str] | None:
    """(tür, değer) döndürür; ör. ("xpath", "//button[@id='submit-btn']")."""
    m = _JSON_RE.search(error_message)
    if m:
        method = _METHOD_NORMALIZE.get(m.group(1), m.group(1))
        value = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
        return method, value
    m = _BY_RE.search(error_message)
    if m:
        return _METHOD_NORMALIZE.get(m.group(1), m.group(1)), m.group(2).strip()
    return None


def find_occurrences(root: Path, subdirs: list[str],
                     needle: str) -> list[tuple[Path, int]]:
    """Whitelist dizinleri altındaki metin dosyalarında `needle` ara.

    [(dosya, eşleşme sayısı), ...] döndürür — agent'ın prompt'una "muhtemelen
    şu dosyaya bakın" ipucu eklemek için; bulunamazsa (boş liste) sorun
    değil, agent repoyu kendisi tarar."""
    hits: list[tuple[Path, int]] = []
    for sub in subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (UnicodeDecodeError, OSError):
                continue
            count = text.count(needle)
            if count:
                hits.append((path, count))
    return hits


def code_excerpt(path: Path, needle: str, context: int = 8) -> str:
    """Locator'ın geçtiği yerin çevresinden kod kesiti."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            return "\n".join(f"{n + 1}: {lines[n]}" for n in range(start, end))
    return ""
