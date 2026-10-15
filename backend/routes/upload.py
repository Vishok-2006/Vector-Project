import asyncio
import logging
import posixpath
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import database
from config import get_settings
from embeddings.generate import EmbeddingError, get_embeddings, max_chunk_words
from qdrant_store import VectorStoreError, get_store
from security import current_user
from services.parsers import PdfError, chunk_text, extract_text_from_pdf

router = APIRouter()
logger = logging.getLogger(__name__)

MIN_CHUNK_WORDS = 50


def _clean_filename(raw: str | None) -> str:
    """Keep only a safe base name; the name is metadata, never used as a filesystem path."""
    name = posixpath.basename((raw or "").replace("\\", "/")).strip()
    return name[:200]


def _record_failure(responses: list, user_id: str, filename: str, message: str) -> None:
    responses.append({"filename": filename or "unnamed", "status": "error", "error": message})
    # Never overwrite a good, already-indexed document's status with a failed re-upload.
    if filename and not database.get_document_by_filename(user_id, filename):
        database.add_document(user_id, filename, "error")


def _process_pdf(user_id: str, filename: str, data: bytes, chunk_size: int) -> dict:
    """CPU/IO heavy pipeline, run in a worker thread: parse -> chunk -> embed -> index."""
    pages = extract_text_from_pdf(data, filename)
    if not pages:
        raise PdfError("No extractable text found in PDF (it may be scanned images).")

    chunks = chunk_text(pages, chunk_size)
    embeddings = get_embeddings([c["text"] for c in chunks])

    store = get_store()
    upload_id = uuid.uuid4().hex
    # Write the new version first, then drop the old one: a failed re-upload can never
    # leave the user without their previously indexed copy.
    store.upsert_chunks(user_id, upload_id, chunks, embeddings)
    store.delete_stale_versions(user_id, filename, keep_upload_id=upload_id)
    return {"chunks": len(chunks)}


@router.post("/upload")
async def upload_pdfs(
    files: List[UploadFile] = File(...),
    chunk_size: Optional[int] = 500,
    user_id: str = Depends(current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    applied_chunk_size = max(MIN_CHUNK_WORDS, min(int(chunk_size or 500), max_chunk_words()))
    responses = []

    for upload in files:
        filename = _clean_filename(upload.filename)

        if not filename.lower().endswith(".pdf"):
            _record_failure(responses, user_id, filename, "Not a PDF")
            continue

        try:
            data = await upload.read()
            if len(data) > max_bytes:
                _record_failure(responses, user_id, filename, f"File is larger than the {settings.max_upload_mb} MB limit")
                continue

            result = await asyncio.to_thread(_process_pdf, user_id, filename, data, applied_chunk_size)
            await asyncio.to_thread(database.add_document, user_id, filename, "success", result["chunks"])
            responses.append(
                {
                    "filename": filename,
                    "status": "success",
                    "chunks": result["chunks"],
                    "chunk_size_applied": applied_chunk_size,
                }
            )
        except (PdfError, EmbeddingError, VectorStoreError) as exc:
            logger.warning("Upload of %r failed: %s", filename, exc)
            _record_failure(responses, user_id, filename, str(exc))
        except Exception:
            logger.exception("Unexpected error while processing %r", filename)
            _record_failure(responses, user_id, filename, "Unexpected error while processing this file. See server logs.")

    return {"results": responses}


@router.get("/documents")
def list_documents(user_id: str = Depends(current_user)):
    return database.get_all_documents(user_id)


@router.delete("/documents/{document_id}")
def remove_document(document_id: int, user_id: str = Depends(current_user)):
    document = database.get_document(user_id, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        get_store().delete_document(user_id, document["filename"])
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    database.delete_document(user_id, document_id)
    return {"status": "success"}
