"""OpenAI-uyumlu endpoint'e (vLLM/Ollama) tek atımlık chat çağrısı."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import HealError


def chat_completion(base_url: str, model: str, prompt: str,
                    api_key_env: str | None = None,
                    timeout: int = 300) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key_env and os.environ.get(api_key_env):
        headers["Authorization"] = f"Bearer {os.environ[api_key_env]}"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers,
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HealError(f"LLM çağrısı başarısız ({url}): {exc}") from exc
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise HealError(f"LLM cevabı beklenen biçimde değil: "
                        f"{str(payload)[:300]}") from exc


def extract_json_block(text: str) -> dict:
    """Model cevabındaki ilk geçerli JSON nesnesini çıkarır
    (markdown çiti, açıklama metni vb. toleranslı)."""
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise HealError(f"LLM cevabında geçerli JSON bulunamadı: {text[:300]}")
