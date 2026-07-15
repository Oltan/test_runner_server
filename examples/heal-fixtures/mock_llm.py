#!/usr/bin/env python3
"""OpenAI-uyumlu SAHTE LLM sunucusu (port 8199).

Healing Mod A'yı vLLM kurulu olmadan test etmek içindir: her chat isteğine
heal-fixture-a'nın beklediği locator düzeltmesini döndürür. Gelen son prompt
mock_llm_last_prompt.txt'ye yazılır — motorun LLM'e gerçekte ne gönderdiğini
(budanmış DOM adayları vb.) buradan inceleyebilirsiniz.

Kullanım:  python3 examples/heal-fixtures/mock_llm.py &
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 8199
LOG = Path(__file__).parent / "mock_llm_last_prompt.txt"

ANSWER = {
    "selector_type": "xpath",
    "selector": "//button[@id='submit-button-v2']",
    "reason": "submit butonunun id'si submit-button-v2 olarak değişmiş",
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        LOG.write_text(body["messages"][0]["content"], encoding="utf-8")
        response = {
            "choices": [{"message": {
                "role": "assistant",
                "content": "İşte düzeltme:\n```json\n"
                           + json.dumps(ANSWER, ensure_ascii=False) + "\n```",
            }}]
        }
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # sessiz çalış
        pass


if __name__ == "__main__":
    print(f"Mock LLM dinliyor: http://127.0.0.1:{PORT}/v1/chat/completions")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
