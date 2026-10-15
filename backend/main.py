import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config  # loads .env before anything reads the environment

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [backend:%(name)s] %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Qdrant/NIM call is noise
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("vectora")

import database
from qdrant_store import VectorStoreMisconfigured, get_store
from routes.query import router as query_router
from routes.system import router as system_router
from routes.upload import router as upload_router
from routes.vector_store import router as vector_router
from services import llm_service


def _connect_vector_store() -> None:
    """Wait for Qdrant in the background so the API (and /api/health) are reachable
    immediately and report progress instead of the process blocking or crashing."""
    try:
        get_store().wait_until_ready()
    except VectorStoreMisconfigured:
        pass  # already logged as an error; /api/health reports it and no data is touched
    except Exception as exc:
        logger.error("Qdrant did not become ready: %s (will keep retrying on demand)", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.get_settings()
    database.init_db()
    llm = llm_service.get_llm_runtime_config()
    logger.info(
        "%s %s starting. chat_model=%s embeddings=%s/%s(%dd) qdrant=%s collection=%s data_dir=%s",
        config.APP_NAME,
        config.APP_VERSION,
        llm["model"],
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_dimension,
        settings.qdrant_url,
        settings.qdrant_collection,
        settings.data_dir,
    )
    if not llm["configured"]:
        logger.warning("NVIDIA_API_KEY is not set: chat and uploads will fail until it is configured.")

    threading.Thread(target=_connect_vector_store, name="qdrant-startup", daemon=True).start()
    yield
    logger.info("Shutting down.")
    get_store().close()


app = FastAPI(
    title="Vectora API",
    description="Backend API for Vectora - a multi-PDF research assistant using NVIDIA NIM and Qdrant.",
    version=config.APP_VERSION,
    lifespan=lifespan,
)

# Same-origin by default (the reverse proxy serves UI and API together). Cross-origin access
# is opt-in through an explicit allow-list; a wildcard is never combined with credentials.
_origins = config.get_settings().cors_origins
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(system_router, prefix="/api", tags=["System"])
app.include_router(upload_router, prefix="/api", tags=["Upload"])
app.include_router(query_router, prefix="/api", tags=["Chat"])
app.include_router(vector_router, prefix="/api", tags=["Vector Store"])


@app.get("/")
def root():
    return {"status": "Backend running", "app": config.APP_NAME}
