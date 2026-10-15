"""A tiny fake of NVIDIA NIM's OpenAI-compatible API (chat + embeddings).

Used by the tests and for offline smoke tests of the whole container::

    python -m tests.fake_nim --port 9999 --key test-key
    # then run the app with NVIDIA_BASE_URL=http://127.0.0.1:9999/v1 NVIDIA_API_KEY=test-key

Behaviour mirrors the real service where it matters:
* requires ``Authorization: Bearer <key>`` (401 otherwise)
* ``nemotron``/``embedqa`` models reject requests without ``input_type`` (HTTP 400), like the real NIM
* embeddings are deterministic hashed bag-of-words vectors (2048-d, like nemotron-3-embed-1b), so semantic search is
  testable: texts sharing words get a high cosine similarity.
* chat answers quote the retrieved context so tests can verify RAG grounding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EMBED_DIM = 2048


def embed_text(text: str, dim: int = EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(word.encode()).digest()
        vec[int.from_bytes(digest[:4], "big") % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeNimState:
    def __init__(self, api_key: str = "test-key") -> None:
        self.api_key = api_key
        self.lock = threading.Lock()
        self.chat_requests: list[dict] = []
        self.embedding_requests: list[dict] = []
        # {"status": 429, "remaining": 2, "path": "/chat/completions"} -> fail the next N calls
        self.fail: dict | None = None
        self.delay_seconds = 0.0
        self.embed_dim = EMBED_DIM

    def reset(self) -> None:
        with self.lock:
            self.chat_requests.clear()
            self.embedding_requests.clear()
            self.fail = None
            self.delay_seconds = 0.0
            self.embed_dim = EMBED_DIM


def _make_handler(state: FakeNimState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test output quiet
            return

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.rstrip("/") in ("/health", "/v1/health"):
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"detail": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            path = self.path.split("?")[0]

            if state.delay_seconds:
                time.sleep(state.delay_seconds)

            if self.headers.get("Authorization") != f"Bearer {state.api_key}":
                return self._send(401, {"status": 401, "title": "Unauthorized", "detail": "Authentication failed"})

            with state.lock:
                fail = state.fail
                if fail and fail.get("remaining", 0) > 0 and fail.get("path", path) in path:
                    fail["remaining"] -= 1
                    return self._send(fail["status"], {"detail": f"injected failure {fail['status']}"})

            if path.endswith("/chat/completions"):
                with state.lock:
                    state.chat_requests.append(payload)
                if payload.get("model") == "missing/model":
                    return self._send(404, {"detail": "Function not found for the given model"})
                user_msg = payload["messages"][-1]["content"]
                wants_title = "Generate a very short title" in user_msg
                if wants_title:
                    answer = "Fake Chat Title"
                else:
                    context = user_msg.split("Question:")[0].replace("Context:\n", "").strip()
                    answer = f"<think>reasoning here</think>Answer: Based on context -> {context[:600]}"
                return self._send(
                    200,
                    {
                        "id": "chatcmpl-fake",
                        "object": "chat.completion",
                        "model": payload.get("model"),
                        "choices": [
                            {"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
                        ],
                    },
                )

            if path.endswith("/embeddings"):
                with state.lock:
                    state.embedding_requests.append(payload)
                model = payload.get("model", "")
                if model == "nvidia/nv-embedqa-e5-v5":
                    return self._send(
                        410,
                        {"detail": f"The model '{model}' has reached its end of life and is no longer available."},
                    )
                if ("embedqa" in model or "nemotron" in model) and payload.get("input_type") not in (
                    "query",
                    "passage",
                ):
                    return self._send(
                        400, {"detail": "'input_type' parameter is required for asymmetric models"}
                    )
                inputs = payload["input"]
                if isinstance(inputs, str):
                    inputs = [inputs]
                data = [
                    {"object": "embedding", "index": i, "embedding": embed_text(text, state.embed_dim)}
                    for i, text in enumerate(inputs)
                ]
                return self._send(200, {"object": "list", "data": data, "model": model})

            self._send(404, {"detail": "not found"})

    return Handler


def start_server(port: int = 0, api_key: str = "test-key") -> tuple[ThreadingHTTPServer, FakeNimState]:
    state = FakeNimState(api_key)
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(state))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="fake-nim", daemon=True).start()
    return server, state


if __name__ == "__main__":  # pragma: no cover - manual / container smoke use
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--key", default="test-key")
    args = parser.parse_args()
    server, _ = start_server(args.port, args.key)
    print(f"fake NIM listening on http://127.0.0.1:{server.server_address[1]}/v1 (key={args.key})", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
