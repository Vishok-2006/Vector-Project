"""Text embeddings - deliberately independent from the chat model.

The NIM *chat* model cannot produce embeddings, so retrieval uses a dedicated
embedding model:

* ``EMBEDDING_PROVIDER=nvidia`` (default): NIM ``/embeddings`` with
  ``nvidia/nv-embedqa-e5-v5`` (1024-dim). Asymmetric: passages are embedded with
  ``input_type=passage`` and queries with ``input_type=query``.
* ``EMBEDDING_PROVIDER=local``: sentence-transformers running inside the container
  (384-dim ``all-MiniLM-L6-v2``). Needs the optional ``requirements-local.txt``.

Every returned vector is checked against ``EMBEDDING_DIMENSION`` so a mismatch
fails loudly instead of corrupting the index.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache

from config import get_settings
from services.nim import NimClient, NimError

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Embedding generation failed (message is safe to show to users)."""


_client_lock = threading.Lock()
_nim_client: NimClient | None = None
_nim_client_key: tuple | None = None


def _get_nim_client() -> NimClient:
    global _nim_client, _nim_client_key
    settings = get_settings()
    key = (settings.embedding_base_url, settings.nvidia_api_key, settings.llm_timeout_seconds)
    with _client_lock:
        if _nim_client is None or _nim_client_key != key:
            if _nim_client is not None:
                _nim_client.close()
            _nim_client = NimClient(
                base_url=settings.embedding_base_url,
                api_key=settings.nvidia_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
            _nim_client_key = key
        return _nim_client


@lru_cache(maxsize=1)
def _local_model(name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise EmbeddingError(
            "EMBEDDING_PROVIDER=local requires sentence-transformers. Build the image with "
            "--build-arg EMBEDDINGS=local or `pip install -r backend/requirements-local.txt`."
        ) from exc
    logger.info("Loading local embedding model %s", name)
    return SentenceTransformer(name)


def _check_dimension(vectors: list[list[float]]) -> list[list[float]]:
    expected = get_settings().embedding_dimension
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingError(
                f"Embedding model '{get_settings().embedding_model}' returned {len(vector)}-dimensional "
                f"vectors but EMBEDDING_DIMENSION is {expected}. Fix EMBEDDING_DIMENSION/EMBEDDING_MODEL."
            )
    return vectors


def _embed_nvidia(texts: list[str], input_type: str) -> list[list[float]]:
    settings = get_settings()
    client = _get_nim_client()
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), settings.embedding_batch_size):
            batch = texts[start : start + settings.embedding_batch_size]
            vectors.extend(
                client.embeddings(
                    settings.embedding_model,
                    batch,
                    input_type=input_type if settings.embedding_asymmetric else None,
                )
            )
    except NimError as exc:
        raise EmbeddingError(f"Embedding request failed: {exc}") from exc
    return vectors


def _embed_local(texts: list[str]) -> list[list[float]]:
    model = _local_model(get_settings().embedding_model)
    return model.encode(texts, show_progress_bar=False, batch_size=32).tolist()


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    if not texts:
        return []
    cleaned = [t if t.strip() else " " for t in texts]
    if get_settings().embedding_provider == "local":
        vectors = _embed_local(cleaned)
    else:
        vectors = _embed_nvidia(cleaned, input_type)
    return _check_dimension(vectors)


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed document chunks for indexing."""
    return _embed(texts, "passage")


def get_query_embedding(query: str) -> list[float]:
    """Embed a search query."""
    return _embed([query], "query")[0]


def max_chunk_words() -> int:
    """Largest chunk (in words) that fits the embedding model's context window."""
    return get_settings().embedding_max_chunk_words


def embedding_info() -> dict:
    settings = get_settings()
    return {
        "provider": settings.embedding_provider,
        "model": settings.embedding_model,
        "dimension": settings.embedding_dimension,
        "max_chunk_words": settings.embedding_max_chunk_words,
    }
