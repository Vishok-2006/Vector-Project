"""Qdrant vector store (replaces the former Endee integration).

Design rules
------------
* **No destructive startup.** An existing collection is never deleted, recreated or
  altered. If its vector size, distance metric or embedding model does not match the
  configuration, the store reports ``misconfigured`` and refuses to read/write
  instead of "fixing" it - so a wrong env var cannot wipe indexed documents.
* **Cosine distance.** Both supported embedding models are trained for cosine
  similarity. Qdrant normalises vectors on insert and returns cosine similarity
  (higher = more similar), which is what the retrieval score threshold expects.
* **Per-user isolation.** Every point carries ``user_id`` in its payload and every
  search / count / scroll / delete is filtered by it. ``user_id`` is indexed as a
  tenant key so filtered search stays fast with many users.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from config import Settings, get_settings

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 128


class VectorStoreError(RuntimeError):
    """The vector store is unreachable or an operation failed."""


class VectorStoreMisconfigured(VectorStoreError):
    """The existing collection is incompatible with the configured embeddings.

    Deliberately *not* auto-repaired, because the only repair is deleting data.
    """


def _user_filter(user_id: str, *extra: qm.Condition, must_not: list[qm.Condition] | None = None) -> qm.Filter:
    if not user_id:
        # Defence in depth: an empty id would otherwise match legacy/untagged data.
        raise ValueError("user_id is required for every vector-store operation")
    must: list[qm.Condition] = [qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id))]
    must.extend(extra)
    return qm.Filter(must=must, must_not=must_not or None)


def _match(key: str, value: Any) -> qm.FieldCondition:
    return qm.FieldCondition(key=key, match=qm.MatchValue(value=value))


class VectorStore:
    def __init__(self, settings: Settings | None = None, client: QdrantClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.collection = self.settings.qdrant_collection
        self.dimension = self.settings.embedding_dimension
        self._client = client
        self._lock = threading.Lock()
        self._ready = False
        self._error: str | None = None
        self._misconfigured = False

    # ------------------------------------------------------------------ client

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key or None,
                timeout=30,
                prefer_grpc=False,
                check_compatibility=False,  # client and server versions are pinned together
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - best effort on shutdown
                pass

    # -------------------------------------------------------------- readiness

    def ensure_ready(self) -> None:
        """Make sure the collection exists and is compatible. Idempotent and cheap."""
        if self._ready:
            return
        if self._misconfigured and self._error:
            raise VectorStoreMisconfigured(self._error)
        with self._lock:
            if self._ready:
                return
            try:
                self._ensure_collection()
            except VectorStoreMisconfigured as exc:
                self._misconfigured = True
                self._error = str(exc)
                logger.error("Vector store misconfigured: %s", exc)
                raise
            except Exception as exc:
                self._error = f"Qdrant is not reachable at {self.settings.qdrant_url}: {exc}"
                raise VectorStoreError(self._error) from exc
            self._ready = True
            self._error = None

    def wait_until_ready(self, timeout: float | None = None, interval: float = 1.0) -> None:
        """Block until Qdrant answers and the collection is verified (startup ordering)."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.settings.qdrant_startup_timeout_seconds)
        attempt = 0
        while True:
            attempt += 1
            try:
                self.ensure_ready()
                logger.info("Qdrant ready (collection=%s, attempts=%d).", self.collection, attempt)
                return
            except VectorStoreMisconfigured:
                raise  # retrying cannot help
            except VectorStoreError as exc:
                if time.monotonic() >= deadline:
                    raise
                if attempt == 1 or attempt % 5 == 0:
                    logger.info("Waiting for Qdrant... (%s)", exc)
                time.sleep(interval)

    def status(self) -> dict[str, Any]:
        """Health snapshot for /api/health. Never raises."""
        info: dict[str, Any] = {
            "backend": "qdrant",
            "collection": self.collection,
            "dimension": self.dimension,
            "distance": "Cosine",
        }
        try:
            self.ensure_ready()
            # Live probe: ensure_ready() is cached, so verify Qdrant still answers
            # (it may have crashed or restarted since startup).
            if not self.client.collection_exists(self.collection):
                self.mark_unready()
                self.ensure_ready()  # recreates only if it is genuinely missing
            info.update(ok=True, state="ready")
        except VectorStoreMisconfigured as exc:
            info.update(ok=False, state="misconfigured", error=str(exc))
        except VectorStoreError as exc:
            info.update(ok=False, state="unreachable", error=str(exc))
        except Exception as exc:
            self.mark_unready()
            info.update(ok=False, state="unreachable", error=f"Qdrant probe failed: {exc}")
        return info

    def mark_unready(self) -> None:
        """Re-verify on next use (e.g. after Qdrant restarted)."""
        if not self._misconfigured:
            self._ready = False

    # ------------------------------------------------------------- collection

    def _expected_metadata(self) -> dict[str, Any]:
        return {
            "embedding_provider": self.settings.embedding_provider,
            "embedding_model": self.settings.embedding_model,
            "embedding_dimension": self.dimension,
            "app": "vectora",
        }

    def _ensure_collection(self) -> None:
        client = self.client
        if client.collection_exists(self.collection):
            self._verify_existing()
        else:
            logger.info(
                "Creating Qdrant collection %r (size=%d, distance=Cosine).", self.collection, self.dimension
            )
            try:
                client.create_collection(
                    collection_name=self.collection,
                    vectors_config=qm.VectorParams(size=self.dimension, distance=qm.Distance.COSINE),
                    on_disk_payload=True,
                    metadata=self._expected_metadata(),
                )
            except Exception:
                # Lost a creation race, or an old server without `metadata` support.
                if not client.collection_exists(self.collection):
                    raise
                self._verify_existing()
        self._ensure_payload_indexes()

    def _verify_existing(self) -> None:
        info = self.client.get_collection(self.collection)
        params = info.config.params
        vectors = params.vectors
        if not isinstance(vectors, qm.VectorParams):
            raise VectorStoreMisconfigured(
                f"Qdrant collection {self.collection!r} uses named/multiple vectors, which this app "
                "does not support. Point QDRANT_COLLECTION at a different name."
            )
        if vectors.size != self.dimension:
            raise VectorStoreMisconfigured(
                f"Qdrant collection {self.collection!r} stores {vectors.size}-dimensional vectors but "
                f"the configured embedding model ({self.settings.embedding_model}) produces "
                f"{self.dimension}. Existing data was left untouched. Either restore the previous "
                f"EMBEDDING_* settings, or set QDRANT_COLLECTION to a new name and re-upload your documents."
            )
        if vectors.distance != qm.Distance.COSINE:
            raise VectorStoreMisconfigured(
                f"Qdrant collection {self.collection!r} uses {vectors.distance} distance; this app "
                "requires Cosine. Existing data was left untouched; use a different QDRANT_COLLECTION."
            )
        stored = getattr(info.config, "metadata", None) or {}
        stored_model = stored.get("embedding_model")
        if stored_model and stored_model != self.settings.embedding_model:
            raise VectorStoreMisconfigured(
                f"Qdrant collection {self.collection!r} was built with embedding model {stored_model!r} but "
                f"{self.settings.embedding_model!r} is configured. Vectors from different models are not "
                "comparable even when their sizes match. Existing data was left untouched; restore the "
                "old EMBEDDING_MODEL or set QDRANT_COLLECTION to a new name and re-upload."
            )

    def _ensure_payload_indexes(self) -> None:
        # Creating an index that already exists is a no-op, so this is safe on every start.
        try:
            self.client.create_payload_index(
                self.collection,
                field_name="user_id",
                field_schema=qm.KeywordIndexParams(type=qm.KeywordIndexType.KEYWORD, is_tenant=True),
            )
        except Exception:
            # Older servers without tenant-index support: fall back to a plain keyword index.
            self.client.create_payload_index(
                self.collection, field_name="user_id", field_schema=qm.PayloadSchemaType.KEYWORD
            )
        for field in ("filename", "upload_id"):
            self.client.create_payload_index(
                self.collection, field_name=field, field_schema=qm.PayloadSchemaType.KEYWORD
            )

    # ------------------------------------------------------------------ writes

    def _wrap(self, action: str, exc: Exception) -> VectorStoreError:
        self.mark_unready()
        return VectorStoreError(f"Qdrant {action} failed: {exc}")

    def upsert_chunks(
        self,
        user_id: str,
        upload_id: str,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> int:
        """Store chunks ({id, text, metadata:{filename,page}}) with their vectors."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not user_id:
            raise ValueError("user_id is required")
        self.ensure_ready()
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
            if len(vector) != self.dimension:
                raise VectorStoreError(
                    f"Embedding has {len(vector)} dimensions but the collection expects {self.dimension}."
                )
            metadata = chunk["metadata"]
            points.append(
                qm.PointStruct(
                    id=chunk["id"],
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "upload_id": upload_id,
                        "filename": metadata["filename"],
                        "page": metadata.get("page", 0),
                        "chunk_index": index,
                        "text": chunk["text"],
                    },
                )
            )
        try:
            for start in range(0, len(points), UPSERT_BATCH_SIZE):
                self.client.upsert(
                    collection_name=self.collection,
                    points=points[start : start + UPSERT_BATCH_SIZE],
                    wait=True,
                )
        except Exception as exc:
            raise self._wrap("upsert", exc) from exc
        return len(points)

    def delete_stale_versions(self, user_id: str, filename: str, keep_upload_id: str) -> None:
        """After a re-upload, drop the previous version's chunks (new ones are already stored)."""
        flt = _user_filter(
            user_id, _match("filename", filename), must_not=[_match("upload_id", keep_upload_id)]
        )
        self.ensure_ready()
        try:
            self.client.delete(
                collection_name=self.collection, points_selector=qm.FilterSelector(filter=flt), wait=True
            )
        except Exception as exc:
            raise self._wrap("delete", exc) from exc

    def delete_document(self, user_id: str, filename: str) -> None:
        flt = _user_filter(user_id, _match("filename", filename))
        self.ensure_ready()
        try:
            self.client.delete(
                collection_name=self.collection, points_selector=qm.FilterSelector(filter=flt), wait=True
            )
        except Exception as exc:
            raise self._wrap("delete", exc) from exc

    def delete_user_data(self, user_id: str) -> None:
        """Remove ONLY this user's vectors. The collection itself is never dropped."""
        flt = _user_filter(user_id)
        self.ensure_ready()
        try:
            self.client.delete(
                collection_name=self.collection, points_selector=qm.FilterSelector(filter=flt), wait=True
            )
        except Exception as exc:
            raise self._wrap("delete", exc) from exc

    # ------------------------------------------------------------------- reads

    def search(self, user_id: str, vector: list[float], top_k: int = 5) -> list[dict]:
        """Semantic search within one user's chunks. Returns dicts sorted by cosine score."""
        flt = _user_filter(user_id)
        self.ensure_ready()
        if len(vector) != self.dimension:
            raise VectorStoreError(
                f"Query embedding has {len(vector)} dimensions but the collection expects {self.dimension}."
            )
        try:
            response = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                query_filter=flt,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise self._wrap("search", exc) from exc
        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                {
                    "score": float(point.score),
                    "filename": payload.get("filename", "unknown"),
                    "page": payload.get("page", 0),
                    "text": payload.get("text", ""),
                }
            )
        return results

    def count(self, user_id: str) -> int:
        flt = _user_filter(user_id)
        self.ensure_ready()
        try:
            return int(
                self.client.count(collection_name=self.collection, count_filter=flt, exact=True).count
            )
        except Exception as exc:
            raise self._wrap("count", exc) from exc

    def sample_chunks(self, user_id: str, limit: int = 10) -> list[dict]:
        flt = _user_filter(user_id)
        self.ensure_ready()
        try:
            points, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=flt,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise self._wrap("scroll", exc) from exc
        return [
            {
                "id": str(point.id),
                "filename": (point.payload or {}).get("filename", "unknown"),
                "page": (point.payload or {}).get("page", 0),
                "text": ((point.payload or {}).get("text", ""))[:300],
            }
            for point in points
        ]


# ----------------------------------------------------------------- module singleton

_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_store() -> VectorStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = VectorStore()
    return _store


def set_store(store: VectorStore | None) -> None:
    """Replace the singleton (tests, or after changing settings)."""
    global _store
    _store = store
