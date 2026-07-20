#!/usr/bin/env python3
"""opencode başlatıcısı — sunucu Mod B'de `agent.provider: opencode` için
bunu otomatik çalıştırır (cwd = heal worktree'si).

Ortam değişkenleri (sunucu set eder / config'ten gelir):
  HEAL_PROMPT_FILE  görev dosyası (içeriği prompt olarak geçilir)
  HEAL_MODEL        model (örn. vllm/glm-5.2-fp8 — opencode.json'daki provider adıyla)
  HEAL_AGENT_BIN    opencode çalıştırılabilir yolu (varsayılan: "opencode";
                    Windows'ta tam yol verilebilir)
  HEAL_AGENT_ARGS   ek CLI argümanları (boşlukla ayrılmış, opsiyonel)

Not: opencode, test reponuzun kökündeki opencode.json'dan provider/endpoint
bilgisini, AGENTS.md'den proje kurallarını kendisi okur.
"""
import os
import subprocess
import sys
from pathlib import Path

prompt = Path(os.environ["HEAL_PROMPT_FILE"]).read_text(encoding="utf-8")
model = os.environ.get("HEAL_MODEL", "")
binary = os.environ.get("HEAL_AGENT_BIN", "opencode")
extra = os.environ.get("HEAL_AGENT_ARGS", "").split()

cmd = [binary, "run"]
if model:
    cmd += ["--model", model]
cmd += [*extra, prompt]

sys.exit(subprocess.run(cmd).returncode)
