from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

from routes.upload import router as upload_router
from routes.query import router as query_router

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
app.include_router(query_router, prefix="/api", tags=["Query"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend is running flawlessly"}

@app.get("/")
def root():
    return {"status": "Backend running"}
