"""Deterministik patch ve diff whitelist kontrolleri.

Mod A: LLM'in önerdiği yeni locator, kod içinde TEK eşleşme varsa
literal olarak değiştirilir; birden çok eşleşme = insan onayına düşer.
Mod B: agent bittikten sonra `git status` çıktısı whitelist ile
karşılaştırılır — dışarıya dokunulduysa heal reddedilir.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import HealError
from .locator import find_occurrences


def apply_single_literal_patch(root: Path, subdirs: list[str],
                               old: str, new: str) -> Path:
    """`old` metnini whitelist altında tam bir yerde `new` ile değiştirir."""
    hits = find_occurrences(root, subdirs, old)
    total = sum(count for _, count in hits)
    if total == 0:
        raise HealError(
            f"Kırılan locator kod içinde bulunamadı: {old!r} "
            f"(aranan dizinler: {subdirs})")
    if total > 1:
        places = ", ".join(f"{p.relative_to(root)}×{c}" for p, c in hits)
        raise HealError(
            f"Locator {total} yerde geçiyor ({places}) — otomatik patch "
            "güvenli değil, insan onayı gerekir.")
    path, _ = hits[0]
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def changed_paths(worktree: Path) -> list[str]:
    """Worktree'deki değişen/yeni dosyaların repo-göreli yolları."""
    # -uall: untracked dosyaları dizin olarak toplamadan tek tek listele
    result = subprocess.run(
        ["git", "status", "--porcelain", "-uall"], cwd=worktree,
        capture_output=True, text=True, check=True)
    paths = []
    for line in result.stdout.splitlines():
        entry = line[3:].strip()
        if " -> " in entry:  # rename: yeni adı al
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip('"'))
    return paths


def whitelist_violations(worktree: Path, whitelist: list[str]) -> list[str]:
    """Whitelist dışında değişen dosyalar (boşsa temiz)."""
    normalized = tuple(w.rstrip("/") + "/" for w in whitelist)
    violations = []
    for path in changed_paths(worktree):
        posix = path.replace("\\", "/")
        if not posix.startswith(normalized):
            violations.append(posix)
    return violations
