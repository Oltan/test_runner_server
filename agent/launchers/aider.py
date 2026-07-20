#!/usr/bin/env python3
"""aider başlatıcısı — sunucu Mod B'de `agent.provider: aider` için bunu
otomatik çalıştırır (cwd = heal worktree'si).

Ortam değişkenleri:
  HEAL_PROMPT_FILE  görev dosyası (--message-file ile geçilir)
  HEAL_MODEL        model (örn. openai/glm-5.2-fp8; opsiyonel)
  HEAL_AGENT_BIN    aider çalıştırılabilir yolu (varsayılan: "aider")
  HEAL_AGENT_ARGS   ek CLI argümanları (opsiyonel)

vLLM endpoint'i projects.yaml'da agent.env ile verin:
  env:
    OPENAI_API_BASE: "http://vllm-sunucu:8000/v1"
    OPENAI_API_KEY: "dummy"

--no-auto-commits sabittir: commit'i healing motoru kendisi atar.
"""
import os
import subprocess
import sys

prompt_file = os.environ["HEAL_PROMPT_FILE"]
model = os.environ.get("HEAL_MODEL", "")
binary = os.environ.get("HEAL_AGENT_BIN", "aider")
extra = os.environ.get("HEAL_AGENT_ARGS", "").split()

cmd = [binary, "--yes-always", "--no-auto-commits",
       "--message-file", prompt_file]
if model:
    cmd += ["--model", model]
cmd += extra

sys.exit(subprocess.run(cmd).returncode)
