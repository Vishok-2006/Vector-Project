from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from config import APP_NAME, APP_VERSION
from embeddings.generate import embedding_info
from qdrant_store import get_store
from security import current_user
from services.llm_service import get_llm_runtime_config

router = APIRouter()


@router.get("/session")
def session(user_id: str = Depends(current_user)):
    """Establishes the signed session cookie. The UI calls this once before anything else."""
    return {"status": "ok"}


@router.get("/health")
def health_check():
    """Liveness + readiness. Returns HTTP 503 while any dependency is unusable so the
    platform health check (Render, Docker) can act on it. Never exposes secrets."""
    llm = get_llm_runtime_config()
    vector = get_store().status()

    problems = []
    if not vector["ok"]:
        problems.append(f"vector store: {vector.get('error', vector['state'])}")
    if not llm["configured"]:
        problems.append("NVIDIA_API_KEY is not set")

    body = {
        "status": "ok" if not problems else "degraded",
        "app": APP_NAME,
        "version": APP_VERSION,
        "message": "Backend is running flawlessly" if not problems else "; ".join(problems),
        "llm": {"provider": llm["provider"], "model": llm["model"], "configured": llm["configured"]},
        "embeddings": embedding_info(),
        "vector_store": vector,
    }
    return JSONResponse(body, status_code=200 if not problems else 503)
