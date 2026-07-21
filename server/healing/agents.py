"""Kurulu coding agent CLI'ları (Mod B).

`projects.yaml` → agent.agent_cli ile seçilir; sunucu doğru başlatıcıyı
(agent/launchers/*.py) çalıştırır — komut satırı yazmaya gerek yok.

Önemli: sunucu agent'ın endpoint/model bilgisiyle ilgilenmez. opencode ve
Claude Code kurulumları zaten kendi ayarlarında (opencode.json, claude
config / ANTHROPIC_BASE_URL vb.) şirketinizin LLM endpoint'ine bağlıdır —
sunucu sadece o CLI'yı, terminalden çağırdığınızla birebir aynı şekilde
çalıştırır. `agent_cli: custom` seçilirse `agent_command` zorunludur (tam
kontrol istediğinizde kullanın).
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
}


def build_agent_command(agent_cli: str) -> str:
    """Seçilen CLI için başlatıcı komutunu üretir."""
    if agent_cli == "custom":
        raise HealError(
            "agent_cli: custom için `agent_command` yazmanız gerekir "
            "(ya da agent_cli'yi opencode/claude-code yapın).")
    launcher_name = _LAUNCHERS.get(agent_cli)
    if launcher_name is None:
        raise HealError(
            f"Bilinmeyen agent_cli: {agent_cli!r} — geçerli değerler: "
            f"{', '.join([*_LAUNCHERS, 'custom'])}")
    launcher = LAUNCHERS_DIR / launcher_name
    if not launcher.is_file():
        raise HealError(f"Başlatıcı bulunamadı: {launcher}")
    return f'"{sys.executable}" "{launcher}"'
