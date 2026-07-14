"""Git worktree izolasyonu: her heal denemesi kendi worktree'sinde ve
kendi branch'inde çalışır; canlı test koşumlarının kullandığı dizine
asla dokunulmaz. Onaylanırsa branch kalır, reddedilirse silinir."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import HealError

_GIT_IDENT = ["-c", "user.name=test-runner-heal",
              "-c", "user.email=heal@test-runner.local"]


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *_GIT_IDENT, *args], cwd=cwd,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise HealError(f"git {' '.join(args[:2])} başarısız: "
                        f"{result.stderr.strip()[:500]}")
    return result.stdout


def is_git_repo(path: Path) -> bool:
    result = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=path,
                            capture_output=True, text=True)
    return result.returncode == 0


def create_worktree(repo_root: Path, dest: Path, branch: str) -> None:
    if not is_git_repo(repo_root):
        raise HealError(
            f"Proje bir git deposu değil: {repo_root} — healing için proje "
            "git ile versiyonlanmış olmalı.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "worktree", "add", "-b", branch, str(dest), "HEAD")


def stage_and_diff(worktree: Path) -> str:
    """Tüm değişiklikleri stage'e alır ve diff'ini döndürür."""
    _git(worktree, "add", "-A")
    return _git(worktree, "diff", "--cached")


def commit(worktree: Path, message: str) -> None:
    _git(worktree, "commit", "-m", message)


def cleanup(repo_root: Path, dest: Path, branch: str,
            keep_branch: bool) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(dest)],
                   cwd=repo_root, capture_output=True, text=True)
    if not keep_branch:
        subprocess.run(["git", "branch", "-D", branch],
                       cwd=repo_root, capture_output=True, text=True)
