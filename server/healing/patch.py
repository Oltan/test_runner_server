"""Diff whitelist kontrolü.

Agent (opencode/Claude Code) bittikten sonra `git status` çıktısı
whitelist ile karşılaştırılır — dışarıya dokunulduysa heal reddedilir.
Kod düzenlemeyi (dosya bulma, satır değiştirme) agent'ın kendisi yapar;
sunucu burada sadece sınır kontrolü uygular.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


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
