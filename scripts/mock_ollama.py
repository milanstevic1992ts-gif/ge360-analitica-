import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(
                {
                    "models": [
                        {
                            "name": "qwen2.5:7b",
                            "model": "qwen2.5:7b",
                            "size": 4700000000,
                            "details": {
                                "family": "qwen2",
                                "parameter_size": "7.6B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                    ]
                }
            )
            return
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            request = json.loads(raw.decode("utf-8") or "{}")
            model = request.get("model", "qwen2.5:7b")
            self._send(
                {
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": (
                            "# Sintesi esecutiva\n"
                            "Test GE360 Intelligence completato.\n\n"
                            "# Azioni consigliate\n"
                            "1. Collegare fonti reali.\n"
                            "2. Verificare conversioni."
                        ),
                    },
                    "done": True,
                    "prompt_eval_count": 100,
                    "eval_count": 40,
                    "total_duration": 1000000,
                }
            )
            return
        self._send({"error": "not found"}, 404)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 11434), Handler).serve_forever()
