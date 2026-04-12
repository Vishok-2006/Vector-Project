from fastapi import APIRouter, HTTPException
from endee_client import get_stats, clear_db, get_sample_chunks

router = APIRouter()

@router.get("/vector-store/stats")
async def vector_stats():
    return get_stats()

@router.get("/vector-store/samples")
async def vector_samples():
    return get_sample_chunks()

@router.post("/vector-store/clear")
async def vector_clear():
    success = clear_db()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear vector store")
    return {"status": "success"}
