import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from routes.upload import router as upload_router
from routes.query import router as query_router
from routes.vector_store import router as vector_router

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

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend is running flawlessly"}

@app.get("/")
def root():
    return {"status": "Backend running"}
