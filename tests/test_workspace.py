"""Git worktree izolasyonu: repo tespiti ve nested-repo koruması.

Kullanıcıların en sık düştüğü iki tuzağı hedefler:
1. Test projesinde hiç .git yok (ne kendisinde ne üst dizinlerinde)
2. Test projesi test_runner_server gibi başka bir reponun İÇİNE konmuş —
   git üst dizinlere doğru arandığı için bu durum sessizce yanlış reponun
   worktree'sini açabilir; bunun yerine erken ve net hata bekleriz.
"""
import subprocess

import pytest

from server.healing import HealError
from server.healing.workspace import create_worktree


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=path, check=True)


def test_create_worktree_rejects_non_git_dir(tmp_path):
    plain = tmp_path / "plain-project"
    plain.mkdir()
    with pytest.raises(HealError, match="git deposu değil"):
        create_worktree(plain, tmp_path / "wt", "heal/x")


def test_create_worktree_rejects_project_nested_in_outer_repo(tmp_path):
    """Java projesi kendi .git'ine sahip değil ve başka bir reponun
    (ör. test_runner_server) alt klasörü — worktree açılmamalı,
    net bir hata verilmeli (sessizce yanlış repo checkout edilmemeli)."""
    outer = tmp_path / "test_runner_server"
    outer.mkdir()
    _init_repo(outer)
    nested_project = outer / "my-java-project"
    nested_project.mkdir()

    with pytest.raises(HealError, match="alt klasörü"):
        create_worktree(nested_project, tmp_path / "wt", "heal/x")


def test_create_worktree_succeeds_for_standalone_repo(tmp_path):
    project = tmp_path / "my-java-project"
    project.mkdir()
    _init_repo(project)
    dest = tmp_path / "wt"

    create_worktree(project, dest, "heal/ok")

    assert dest.is_dir()
    branches = subprocess.run(["git", "branch", "--list", "heal/*"],
                              cwd=project, capture_output=True,
                              text=True).stdout
    assert "heal/ok" in branches
