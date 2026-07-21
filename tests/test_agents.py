"""Kurulu agent CLI'ları: agent_cli seçimi + başlatıcıların doğru
argümanlarla CLI'yı çağırdığının testi (sahte binary ile).

Not: opencode/claude-code kendi ayarlarında zaten bir endpoint'e (örn.
şirketin kendi LLM API'si) bağlıdır — sunucu base_url/model bilmez, sadece
CLI'yı terminalden çağırıldığı gibi başlatır. Model, verilirse --model
olarak eklenir; verilmezse CLI'nın kendi varsayılanı kullanılır (bu yüzden
"model verilmeden" durumu da test edilir)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from server.healing import HealError
from server.healing.agents import LAUNCHERS_DIR, build_agent_command

# Sahte agent binary'si: aldığı argümanları JSON olarak dosyaya yazar.
_FAKE_BIN = """\
#!/usr/bin/env python3
import json, sys
from pathlib import Path
Path(__file__).parent.joinpath("captured.json").write_text(
    json.dumps(sys.argv[1:]), encoding="utf-8")
"""


def test_build_agent_command_known_clis():
    for agent_cli, launcher in [("opencode", "opencode.py"),
                                ("claude-code", "claude_code.py")]:
        command = build_agent_command(agent_cli)
        assert launcher in command
        assert sys.executable in command


def test_build_agent_command_custom_requires_command():
    with pytest.raises(HealError, match="agent_command"):
        build_agent_command("custom")


def test_build_agent_command_unknown_cli():
    with pytest.raises(HealError, match="Bilinmeyen"):
        build_agent_command("chatgpt")


def _run_launcher(tmp_path, launcher: str, env_extra: dict) -> list[str]:
    """Başlatıcıyı sahte binary ile çalıştırıp CLI argümanlarını yakalar."""
    fake_bin = tmp_path / ("fake_agent.py")
    fake_bin.write_text(_FAKE_BIN, encoding="utf-8")
    prompt_file = tmp_path / "HEAL_TASK.md"
    prompt_file.write_text("Senaryo: Kampanya sepeti\ngörev...", encoding="utf-8")

    env = {
        **os.environ,
        "HEAL_PROMPT_FILE": str(prompt_file),
        "HEAL_MODEL": "",  # varsayılan: model verilmez (CLI kendi ayarını kullanır)
        # başlatıcılar HEAL_AGENT_BIN'i tek yol olarak alır; test için
        # python yorumlayıcısını sahte script'e yönlendiremeyiz, bu yüzden
        # sahte binary'yi doğrudan çalıştırılabilir yapıyoruz (POSIX).
        "HEAL_AGENT_BIN": str(fake_bin),
        **env_extra,
    }
    if sys.platform != "win32":
        fake_bin.chmod(0o755)
    else:  # Windows'ta .py doğrudan exec edilemez; python üzerinden sarmala
        wrapper = tmp_path / "fake_agent.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{fake_bin}" %*\n',
                           encoding="utf-8")
        env["HEAL_AGENT_BIN"] = str(wrapper)

    result = subprocess.run([sys.executable, str(LAUNCHERS_DIR / launcher)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads((tmp_path / "captured.json").read_text(encoding="utf-8"))


def test_opencode_launcher_without_model_override(tmp_path):
    """Model belirtilmezse --model hiç eklenmez (CLI kendi varsayılanını
    kullanır — şirketin endpoint'i zaten opencode.json'da tanımlıdır)."""
    args = _run_launcher(tmp_path, "opencode.py", {})
    assert args[0] == "run"
    assert "--model" not in args
    assert "Kampanya sepeti" in args[-1]  # prompt içerik olarak geçildi


def test_opencode_launcher_with_model_override(tmp_path):
    args = _run_launcher(tmp_path, "opencode.py", {"HEAL_MODEL": "glm-5.2-fp8"})
    assert args[1:3] == ["--model", "glm-5.2-fp8"]


def test_claude_code_launcher_without_model_override(tmp_path):
    args = _run_launcher(tmp_path, "claude_code.py", {})
    assert args[0] == "-p" and "Kampanya sepeti" in args[1]
    assert "--permission-mode" in args and "acceptEdits" in args
    assert "--allowedTools" in args
    assert "--model" not in args


def test_claude_code_launcher_with_model_override(tmp_path):
    args = _run_launcher(tmp_path, "claude_code.py", {"HEAL_MODEL": "glm-5.2-fp8"})
    assert "--model" in args and "glm-5.2-fp8" in args
