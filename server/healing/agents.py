"""Hazır agent sağlayıcıları (Mod B).

`projects.yaml` → agent.provider ile seçilir; sunucu doğru başlatıcıyı
(agent/launchers/*.py) kendisi çalıştırır — kullanıcı komut satırı yazmaz.
provider: custom seçilirse agent_command zorunludur (tam kontrol).
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import HealError

LAUNCHERS_DIR = (Path(__file__).resolve().parent.parent.parent
                 / "agent" / "launchers")

_LAUNCHERS = {
    "opencode": "opencode.py",
    "claude-code": "claude_code.py",
    "aider": "aider.py",
}


def build_agent_command(provider: str) -> str:
    """Seçilen provider için başlatıcı komutunu üretir."""
    if provider == "custom":
        raise HealError(
            "provider: custom için `agent_command` yazmanız gerekir "
            "(ya da provider'ı opencode/claude-code/aider yapın).")
    launcher_name = _LAUNCHERS.get(provider)
    if launcher_name is None:
        raise HealError(
            f"Bilinmeyen agent provider'ı: {provider!r} — geçerli değerler: "
            f"{', '.join([*_LAUNCHERS, 'custom'])}")
    launcher = LAUNCHERS_DIR / launcher_name
    if not launcher.is_file():
        raise HealError(f"Başlatıcı bulunamadı: {launcher}")
    return f'"{sys.executable}" "{launcher}"'
