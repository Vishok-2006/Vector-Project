import logging

from fastapi import APIRouter, Depends, HTTPException

import database
from qdrant_store import VectorStoreError, get_store
from security import current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/vector-store/stats")
def vector_stats(user_id: str = Depends(current_user)):
    store = get_store()
    stats = {
        "backend": "qdrant",
        "collection": store.collection,
        "dimension": store.dimension,
        "distance": "Cosine",
    }
    try:
        stats.update(total_vectors=store.count(user_id), status="healthy")
    except VectorStoreError as exc:
        # Same graceful behaviour as before: the UI shows 0 rather than an error page.
        logger.warning("Could not read vector stats: %s", exc)
        stats.update(total_vectors=0, status="unavailable", error=str(exc))
    return stats


@router.get("/vector-store/samples")
def vector_samples(user_id: str = Depends(current_user)):
    try:
        return get_store().sample_chunks(user_id)
    except VectorStoreError as exc:
        logger.warning("Could not read sample chunks: %s", exc)
        return []


@router.post("/vector-store/clear")
def vector_clear(user_id: str = Depends(current_user)):
    """Delete the *current user's* vectors and document registry. Other users and the
    collection itself are untouched."""
    try:
        get_store().delete_user_data(user_id)
    except VectorStoreError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear vector store: {exc}") from exc
    database.delete_all_documents(user_id)
    return {"status": "success"}
