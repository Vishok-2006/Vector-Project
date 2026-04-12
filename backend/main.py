import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ENV_PATH = Path(__file__).resolve().with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from routes.upload import router as upload_router
from routes.query import router as query_router
from routes.vector_store import router as vector_router
from services.gemini_service import get_llm_runtime_config, validate_llm_config

app = FastAPI(
    title="Agentic RAG Multi-PDF Assistant",
    description="Backend API for Agentic RAG Multi-PDF Research Assistant using Endee DB and Gemini.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api", tags=["Upload"])
app.include_router(query_router, prefix="", tags=["Chat"])
app.include_router(vector_router, prefix="", tags=["Vector Store"])


@app.on_event("startup")
async def validate_runtime_configuration() -> None:
    config = validate_llm_config()
    logger = logging.getLogger(__name__)
    logger.info(
        "LLM configuration loaded successfully. provider=%s model=%s timeout=%ss",
        config["provider"],
        config["model"],
        config["timeout_seconds"],
    )

@app.get("/health")
def health_check():
    llm_config = get_llm_runtime_config()
    return {
        "status": "ok",
        "message": "Backend is running flawlessly",
        "llm": {
            "provider": llm_config["provider"],
            "model": llm_config["model"],
        },
    }

@app.get("/")
def root():
    return {"status": "Backend running"}
