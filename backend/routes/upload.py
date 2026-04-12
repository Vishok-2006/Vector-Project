from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import List, Optional
import asyncio

from services.parsers import extract_text_from_pdf, chunk_text
from embeddings.generate import get_embeddings
from endee_client import upsert_vectors
from database import add_document, get_all_documents

router = APIRouter()

@router.post("/upload")
async def upload_pdfs(files: List[UploadFile] = File(...), chunk_size: Optional[int] = 500):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    responses = []
    
    for upload in files:
         if not upload.filename.endswith(".pdf"):
             responses.append({"filename": upload.filename, "status": "error", "error": "Not a PDF"})
             continue
             
         try:
             file_bytes = await upload.read()
             # Offload CPU-heavy tasks to asyncio executor
             loop = asyncio.get_event_loop()
             pages = await loop.run_in_executor(None, extract_text_from_pdf, file_bytes, upload.filename)
             
             if not pages:
                 responses.append({"filename": upload.filename, "status": "error", "error": "No text found in PDF"})
                 add_document(upload.filename, "error")
                 continue
                 
             chunks = await loop.run_in_executor(None, chunk_text, pages, chunk_size)
             chunk_texts = [c["text"] for c in chunks]
             
             embeddings = await loop.run_in_executor(None, get_embeddings, chunk_texts)
             await loop.run_in_executor(None, upsert_vectors, chunks, embeddings)
             
             add_document(upload.filename, "success")
             responses.append({
                  "filename": upload.filename,
                  "status": "success",
                  "chunks": len(chunks)
             })
             
         except Exception as e:
             responses.append({"filename": upload.filename, "status": "error", "error": str(e)})
             add_document(upload.filename, "error")

    return {"results": responses}

@router.get("/documents")
async def list_documents():
    return get_all_documents()
