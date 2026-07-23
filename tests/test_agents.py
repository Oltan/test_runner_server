"""Kurulu agent CLI'ları: agent_cli seçimi doğru argv'yi üretiyor mu?

Not: opencode/claude-code kendi ayarlarında zaten bir endpoint'e (örn.
şirketin kendi LLM API'si) bağlıdır — sunucu base_url/model bilmez, sadece
terminalde elle yazacağınız komutu birebir argv listesi olarak çalıştırır
(shell'e hiç girmez — quoting/uzunluk derdi yok). Model verilirse --model
olarak eklenir; verilmezse CLI'nın kendi varsayılanı kullanılır."""
import pytest

from server.healing import HealError
from server.healing.agents import build_agent_argv


def test_opencode_without_model_override():
    argv = build_agent_argv("opencode", "Kampanya sepeti\ngörev...")
    assert argv == ["opencode", "run", "Kampanya sepeti\ngörev..."]


def test_opencode_with_model_override():
    argv = build_agent_argv("opencode", "görev metni", model="sirket/qwen3.6")
    assert argv == ["opencode", "run", "--model", "sirket/qwen3.6", "görev metni"]


def test_opencode_custom_binary_and_extra_args():
    argv = build_agent_argv("opencode", "görev", model="glm-5.2-fp8",
                            binary="C:/tools/opencode.cmd",
                            extra_args=["--verbose"])
    assert argv == ["C:/tools/opencode.cmd", "run", "--model", "glm-5.2-fp8",
                    "--verbose", "görev"]


def test_claude_code_without_model_override():
    argv = build_agent_argv("claude-code", "görev metni")
    assert argv[:2] == ["claude", "-p"]
    assert argv[2] == "görev metni"
    assert "--permission-mode" in argv and "acceptEdits" in argv
    assert "--allowedTools" in argv
    assert "--model" not in argv


def test_claude_code_with_model_override():
    argv = build_agent_argv("claude-code", "görev", model="glm-5.2-fp8")
    assert "--model" in argv and "glm-5.2-fp8" in argv


def test_claude_code_custom_allowed_tools():
    argv = build_agent_argv("claude-code", "görev",
                            allowed_tools="Read,Edit")
    idx = argv.index("--allowedTools")
    assert argv[idx + 1] == "Read,Edit"


def test_unknown_agent_cli_raises():
    with pytest.raises(HealError, match="Bilinmeyen"):
        build_agent_argv("chatgpt", "görev")


def test_prompt_with_special_characters_passes_through_untouched():
    """argv kullanıldığı için shell quoting/kaçış karakteri sorunu olmamalı —
    tırnak, $, backtick, çok satırlı metin bozulmadan geçmeli."""
    tricky = 'Senaryo: "Kilitli kullanıcı"\nHata: $HOME/`whoami` beklenmedik.'
    argv = build_agent_argv("opencode", tricky)
    assert argv[-1] == tricky  # aynen, hiçbir kaçışlama olmadan
