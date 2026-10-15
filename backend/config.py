"""Central, environment-driven configuration for the Vectora backend.

Everything operators may want to change is read here, once, from environment
variables. Nothing secret has a default value.

Settings are resolved lazily through :func:`get_settings` so tests can change
the environment and call :func:`reload_settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env for local development. Real environment variables always win
# (override=False), so container / Render configuration is never shadowed.
load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=False)

APP_NAME = "Vectora"
APP_VERSION = "2.0.0"

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_CHAT_MODEL = "meta/llama-3.3-70b-instruct"
# nv-embedqa-e5-v5 was retired by NVIDIA (HTTP 410 since 2026-08-25). The hosted catalog changes;
# check https://build.nvidia.com or `curl -H "Authorization: Bearer $NVIDIA_API_KEY" $NVIDIA_BASE_URL/models`.
DEFAULT_NVIDIA_EMBEDDING_MODEL = "nvidia/nemotron-3-embed-1b"
DEFAULT_LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Native output dimension of each supported embedding model. EMBEDDING_DIMENSION
# overrides this for models that are not listed here.
KNOWN_EMBEDDING_DIMENSIONS = {
    "nvidia/nemotron-3-embed-1b": 2048,
    "nvidia/llama-nemotron-embed-1b-v2": 2048,
    "nvidia/llama-nemotron-embed-300m-v2": 2048,
    "nvidia/nv-embedqa-e5-v5": 1024,  # retired
    "nvidia/nv-embed-v1": 4096,
    "nvidia/llama-3.2-nv-embedqa-1b-v2": 2048,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
}

# Conservative word budgets so the *whole* chunk fits in the embedding model's
# context window (nemotron-3-embed: 4096 tokens, MiniLM: 256 word-pieces). 1 word ~ 1.3 tokens.
# If you switch to a short-context model (e.g. a 512-token one), lower EMBEDDING_MAX_CHUNK_WORDS.
DEFAULT_MAX_CHUNK_WORDS = {"nvidia": 1500, "local": 150}


class ConfigError(RuntimeError):
    """Raised when an environment variable holds an unusable value."""


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = _str(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be <= {maximum}, got {value}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = _str(name).lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = _str(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be <= {maximum}, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    # --- NVIDIA NIM: chat model -------------------------------------------
    nvidia_api_key: str
    nvidia_base_url: str
    nvidia_model: str
    llm_timeout_seconds: float
    llm_max_tokens: int
    llm_temperature: float
    llm_max_retries: int
    llm_history_messages: int

    # --- Embeddings (a *separate* model from the chat model) -------------------
    embedding_provider: str  # "nvidia" | "local"
    embedding_model: str
    embedding_dimension: int
    embedding_batch_size: int
    embedding_max_chunk_words: int
    embedding_base_url: str
    embedding_asymmetric: bool  # True: send input_type passage/query (nv-embedqa-*, e5)

    # --- Qdrant -------------------------------------------------------------
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    qdrant_startup_timeout_seconds: float

    # --- Retrieval ----------------------------------------------------------
    rag_top_k: int
    rag_min_score: float

    # --- App ----------------------------------------------------------------
    data_dir: Path
    session_secret: str
    cookie_secure: str  # "auto" | "true" | "false"
    max_upload_mb: int
    cors_origins: tuple[str, ...]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "vectora.db"


def _load() -> Settings:
    provider = _str("EMBEDDING_PROVIDER", "nvidia").lower()
    if provider not in {"nvidia", "local"}:
        raise ConfigError("EMBEDDING_PROVIDER must be 'nvidia' or 'local'")

    default_model = (
        DEFAULT_NVIDIA_EMBEDDING_MODEL if provider == "nvidia" else DEFAULT_LOCAL_EMBEDDING_MODEL
    )
    embedding_model = _str("EMBEDDING_MODEL") or _str("NVIDIA_EMBEDDING_MODEL") or default_model

    dimension_override = _int("EMBEDDING_DIMENSION", 0, minimum=0, maximum=65536)
    dimension = dimension_override or KNOWN_EMBEDDING_DIMENSIONS.get(embedding_model, 0)
    if not dimension:
        raise ConfigError(
            f"Unknown output dimension for embedding model {embedding_model!r}. "
            "Set EMBEDDING_DIMENSION to the model's vector size."
        )

    cookie_secure = _str("COOKIE_SECURE", "auto").lower()
    if cookie_secure not in {"auto", "true", "false"}:
        raise ConfigError("COOKIE_SECURE must be 'auto', 'true' or 'false'")

    cors = tuple(o.strip() for o in _str("BACKEND_CORS_ORIGINS").split(",") if o.strip())

    nvidia_base_url = (_str("NVIDIA_BASE_URL") or DEFAULT_NVIDIA_BASE_URL).rstrip("/")

    return Settings(
        nvidia_api_key=_str("NVIDIA_API_KEY"),
        nvidia_base_url=nvidia_base_url,
        nvidia_model=_str("NVIDIA_MODEL") or DEFAULT_NVIDIA_CHAT_MODEL,
        llm_timeout_seconds=_float("LLM_TIMEOUT_SECONDS", 60.0, minimum=1.0, maximum=600.0),
        llm_max_tokens=_int("LLM_MAX_TOKENS", 1024, minimum=16, maximum=32768),
        llm_temperature=_float("LLM_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0),
        llm_max_retries=_int("LLM_MAX_RETRIES", 2, minimum=0, maximum=6),
        llm_history_messages=_int("LLM_HISTORY_MESSAGES", 6, minimum=0, maximum=40),
        embedding_provider=provider,
        embedding_model=embedding_model,
        embedding_dimension=dimension,
        embedding_batch_size=_int("EMBEDDING_BATCH_SIZE", 32, minimum=1, maximum=512),
        embedding_max_chunk_words=_int(
            "EMBEDDING_MAX_CHUNK_WORDS", DEFAULT_MAX_CHUNK_WORDS[provider], minimum=50, maximum=5000
        ),
        # Embeddings use the same NIM endpoint/key unless explicitly overridden.
        embedding_base_url=(_str("NVIDIA_EMBEDDING_BASE_URL") or nvidia_base_url).rstrip("/"),
        embedding_asymmetric=_bool("NVIDIA_EMBEDDING_ASYMMETRIC", True),
        qdrant_url=(_str("QDRANT_URL") or "http://127.0.0.1:6333").rstrip("/"),
        qdrant_api_key=_str("QDRANT_API_KEY"),
        qdrant_collection=_str("QDRANT_COLLECTION") or "vectora_chunks",
        qdrant_startup_timeout_seconds=_float("QDRANT_STARTUP_TIMEOUT_SECONDS", 90.0, minimum=1.0),
        rag_top_k=_int("RAG_TOP_K", 6, minimum=1, maximum=50),
        rag_min_score=_float("RAG_MIN_SCORE", 0.2, minimum=-1.0, maximum=1.0),
        data_dir=Path(_str("APP_DATA_DIR") or Path(__file__).resolve().parent / "data"),
        session_secret=_str("SESSION_SECRET"),
        cookie_secure=cookie_secure,
        max_upload_mb=_int("MAX_UPLOAD_MB", 25, minimum=1, maximum=1024),
        cors_origins=cors,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return _load()


def reload_settings() -> Settings:
    """Drop the cached settings (used by tests after changing os.environ)."""
    get_settings.cache_clear()
    return get_settings()
