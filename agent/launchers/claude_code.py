#!/usr/bin/env python3
"""Claude Code başlatıcısı — sunucu Mod B'de `agent.provider: claude-code`
için bunu otomatik çalıştırır (cwd = heal worktree'si).

Ortam değişkenleri:
  HEAL_PROMPT_FILE     görev dosyası (içeriği -p ile geçilir)
  HEAL_MODEL           model (opsiyonel; --model olarak geçilir)
  HEAL_AGENT_BIN       claude çalıştırılabilir yolu (varsayılan: "claude")
  HEAL_ALLOWED_TOOLS   izinli araçlar (varsayılan: Read,Edit,Write,Grep,Glob,Bash(mvn:*))
  HEAL_AGENT_ARGS      ek CLI argümanları (opsiyonel)

Kendi vLLM'inizle kullanmak için (Anthropic-uyumlu endpoint/router üzerinden)
projects.yaml'da agent.env ile geçin:
  env:
    ANTHROPIC_BASE_URL: "http://vllm-sunucu:8000"
    ANTHROPIC_AUTH_TOKEN: "dummy"
(alan adlarını kurduğunuz sürümün dokümanıyla doğrulayın)
"""
import os
import subprocess
import sys
from pathlib import Path

prompt = Path(os.environ["HEAL_PROMPT_FILE"]).read_text(encoding="utf-8")
model = os.environ.get("HEAL_MODEL", "")
binary = os.environ.get("HEAL_AGENT_BIN", "claude")
allowed = os.environ.get("HEAL_ALLOWED_TOOLS",
                         "Read,Edit,Write,Grep,Glob,Bash(mvn:*)")
extra = os.environ.get("HEAL_AGENT_ARGS", "").split()

cmd = [binary, "-p", prompt,
       "--permission-mode", "acceptEdits",
       "--allowedTools", allowed]
if model:
    cmd += ["--model", model]
cmd += extra

sys.exit(subprocess.run(cmd).returncode)
