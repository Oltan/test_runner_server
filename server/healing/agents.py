"""Kurulu coding agent CLI'ları.

`projects.yaml` → agent.agent_cli ile seçilir. Sunucu, seçilen CLI'yı
**terminalden çağrılmış gibi birebir** invoke eder: gerçek argv listesi
olarak (`subprocess`e liste verilir, shell'e hiç girmez) — tırnak/kaçış
karakteri/uzunluk derdi yok, prompt'un içeriği ne olursa olsun sorunsuz
geçer. Canlı heal logunda görünen komut da tam olarak budur, ör.:

    $ opencode run --model sirket/qwen3.6 "<görev metni>"
    $ claude -p "<görev metni>" --permission-mode acceptEdits ...

Önemli: sunucu agent'ın endpoint/model bilgisiyle ilgilenmez. opencode ve
Claude Code kurulumları zaten kendi ayarlarında (opencode.json, claude
config / ANTHROPIC_BASE_URL vb.) şirketinizin LLM endpoint'ine bağlıdır.
`agent_cli: custom` seçilirse `agent_command` zorunludur (tam kontrol
istediğinizde kullanın — o zaman shell string olarak çalışır).
"""
from __future__ import annotations

from . import HealError

KNOWN_CLIS = ("opencode", "claude-code")
_DEFAULT_ALLOWED_TOOLS = "Read,Edit,Write,Grep,Glob,Bash(mvn:*)"


def build_agent_argv(agent_cli: str, prompt: str, *, model: str = "",
                     binary: str = "", extra_args: list[str] | None = None,
                     allowed_tools: str = "") -> list[str]:
    """Seçilen CLI için gerçek argv listesini üretir — terminalde elle
    yazacağınız komutla birebir aynı sırada/biçimde."""
    extra_args = list(extra_args or [])
    if agent_cli == "opencode":
        argv = [binary or "opencode", "run"]
        if model:
            argv += ["--model", model]
        return argv + extra_args + [prompt]
    if agent_cli == "claude-code":
        argv = [binary or "claude", "-p", prompt,
                "--permission-mode", "acceptEdits",
                "--allowedTools", allowed_tools or _DEFAULT_ALLOWED_TOOLS]
        if model:
            argv += ["--model", model]
        return argv + extra_args
    raise HealError(
        f"Bilinmeyen agent_cli: {agent_cli!r} — geçerli değerler: "
        f"{', '.join([*KNOWN_CLIS, 'custom'])}")
