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
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise HealError(f"git {' '.join(args[:2])} başarısız: "
                        f"{result.stderr.strip()[:500]}")
    return result.stdout


def is_git_repo(path: Path) -> bool:
    result = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=path,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.returncode == 0


def _git_toplevel(path: Path) -> Path | None:
    """`path`'in ait olduğu git reposunun kök dizini (üst dizinlere doğru
    arar — git'in kendi davranışı). Repo değilse None."""
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def create_worktree(repo_root: Path, dest: Path, branch: str) -> None:
    repo_root = repo_root.resolve()
    # dest MUTLAKA mutlak olmalı: git worktree add, cwd=repo_root ile
    # çalışır ve relatif dest'i kendi cwd'sine göre çözer — server'ın
    # kendi cwd'sine göre relatif verilirse worktree yanlış yere (repo_root
    # altına) yazılır ve sonraki adımlar dosyayı "olmayan" yerde arar.
    dest = dest.resolve()
    toplevel = _git_toplevel(repo_root)
    if toplevel is None:
        raise HealError(
            f"Proje bir git deposu değil: {repo_root} — healing için proje "
            "kendi git deposu olmalı: proje dizininde `git init` yapıp en "
            "az bir commit atın.")
    if toplevel != repo_root:
        # git üst dizinlerde ARAR; proje kendi .git'ine sahip değilse başka
        # bir reponun (genelde test_runner_server'ın) alt klasörü sanılır.
        # Bunu sessizce yanlış reponun worktree'sini açmak yerine erken
        # ve net biçimde reddediyoruz.
        raise HealError(
            f"Proje kendi git deposu değil — {toplevel} reposunun bir alt "
            f"klasörü olarak görünüyor ({repo_root}). Test projenizi "
            "bağımsız bir git deposu yapın (kendi .git'i olsun) ve "
            "test_runner_server'ın klasör ağacının DIŞINDA tutun.")
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
                   cwd=repo_root, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    if not keep_branch:
        subprocess.run(["git", "branch", "-D", branch],
                       cwd=repo_root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
