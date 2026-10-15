"""Shared fixtures.

Integration tests run against a REAL Qdrant server process. Point QDRANT_BIN at a
Qdrant binary (https://github.com/qdrant/qdrant/releases); without it those tests
are skipped (unit tests still run).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import fake_nim  # noqa: E402

TEST_API_KEY = "test-key-123"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _find_qdrant_binary() -> str | None:
    candidates = [os.getenv("QDRANT_BIN"), shutil.which("qdrant"), "/opt/qdrant-test/qdrant", "/usr/local/bin/qdrant"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


class QdrantServer:
    """A real Qdrant process with its own storage directory."""

    def __init__(self, binary: str, storage: Path) -> None:
        self.binary = binary
        self.storage = storage
        self.http_port = _free_port()
        self.grpc_port = _free_port()
        self.process: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.http_port}"

    def start(self) -> None:
        self.storage.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "QDRANT__SERVICE__HTTP_PORT": str(self.http_port),
            "QDRANT__SERVICE__GRPC_PORT": str(self.grpc_port),
            "QDRANT__SERVICE__HOST": "127.0.0.1",
            "QDRANT__STORAGE__STORAGE_PATH": str(self.storage / "storage"),
            "QDRANT__STORAGE__SNAPSHOTS_PATH": str(self.storage / "snapshots"),
            "QDRANT__TELEMETRY_DISABLED": "true",
            "QDRANT__LOG_LEVEL": "WARN",
        }
        self.process = subprocess.Popen(
            [self.binary], cwd=self.storage, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.url}/readyz", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        self.stop()
        raise RuntimeError("Qdrant did not become ready")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def restart(self) -> None:
        self.stop()
        self.start()


@pytest.fixture(scope="session")
def qdrant_server(tmp_path_factory):
    binary = _find_qdrant_binary()
    if not binary:
        pytest.skip("Qdrant binary not found (set QDRANT_BIN) - integration tests skipped")
    server = QdrantServer(binary, tmp_path_factory.mktemp("qdrant"))
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope="session")
def nim_server():
    server, state = fake_nim.start_server(api_key=TEST_API_KEY)
    state.base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    yield state
    server.shutdown()


@pytest.fixture
def nim(nim_server):
    nim_server.reset()
    return nim_server


ENV_KEYS = [
    "NVIDIA_API_KEY", "NVIDIA_BASE_URL", "NVIDIA_MODEL", "NVIDIA_EMBEDDING_BASE_URL", "NVIDIA_EMBEDDING_ASYMMETRIC",
    "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "NVIDIA_EMBEDDING_MODEL", "EMBEDDING_DIMENSION", "EMBEDDING_BATCH_SIZE",
    "EMBEDDING_MAX_CHUNK_WORDS", "QDRANT_URL", "QDRANT_API_KEY", "QDRANT_COLLECTION", "QDRANT_STARTUP_TIMEOUT_SECONDS",
    "RAG_TOP_K", "RAG_MIN_SCORE", "APP_DATA_DIR", "SESSION_SECRET", "COOKIE_SECURE", "MAX_UPLOAD_MB",
    "BACKEND_CORS_ORIGINS", "LLM_TIMEOUT_SECONDS", "LLM_MAX_RETRIES", "LLM_MAX_TOKENS", "LLM_TEMPERATURE",
    "LLM_HISTORY_MESSAGES",
]


@pytest.fixture
def configure(monkeypatch, tmp_path):
    """Return ``configure(**env)`` that applies env overrides and resets every cached singleton."""
    import config
    import security
    import qdrant_store
    from embeddings import generate
    from services import llm_service

    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "appdata"))

    def apply(**env):
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, str(value))
        config.reload_settings()
        security.reset_secret_cache()
        qdrant_store.set_store(None)
        llm_service._client = None
        generate._nim_client = None
        return config.get_settings()

    yield apply

    qdrant_store.set_store(None)
    llm_service._client = None
    generate._nim_client = None
    config.get_settings.cache_clear()  # lazy: re-read lazily after monkeypatch restores the env
    security.reset_secret_cache()


@pytest.fixture
def stack_env(configure, qdrant_server, nim):
    """Environment wired to the real Qdrant + fake NIM. Returns the applied settings."""
    return configure(
        NVIDIA_API_KEY=TEST_API_KEY,
        NVIDIA_BASE_URL=nim.base_url,
        QDRANT_URL=qdrant_server.url,
        QDRANT_COLLECTION=f"t_{uuid.uuid4().hex[:10]}",
        LLM_MAX_RETRIES=1,
        LLM_TIMEOUT_SECONDS=10,
    )


@pytest.fixture
def client(stack_env):
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        # wait for the background Qdrant connection like a real deployment would
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if test_client.get("/api/health").status_code == 200:
                break
            time.sleep(0.2)
        yield test_client


@pytest.fixture
def second_client(client):
    """A different browser: same app, separate cookie jar."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as other:
        yield other


def make_pdf_bytes(pages: list[str]) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def make_pdf():
    return make_pdf_bytes
