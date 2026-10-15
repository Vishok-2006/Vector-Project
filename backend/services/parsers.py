"""PDF text extraction and chunking."""

from __future__ import annotations

import uuid

import pymupdf  # PyMuPDF


class PdfError(ValueError):
    """The uploaded file is not a readable PDF (message is user-safe)."""


def extract_text_from_pdf(file_bytes: bytes, filename: str) -> list[dict]:
    """Extract text page by page from raw bytes.

    Returns: list of ``{"page": int, "text": str, "filename": str}`` (pages without text are skipped).
    """
    if not file_bytes.lstrip()[:5] == b"%PDF-":
        raise PdfError("File does not look like a PDF (missing %PDF header).")

    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfError(f"Could not open PDF: {exc}") from exc

    try:
        if doc.needs_pass:
            raise PdfError("PDF is password-protected.")
        pages = []
        for page_num in range(len(doc)):
            text = doc.load_page(page_num).get_text("text").replace("\x00", "").strip()
            if text:
                pages.append({"page": page_num + 1, "text": text, "filename": filename})
        return pages
    finally:
        doc.close()


def chunk_text(pages: list[dict], max_words: int = 500, overlap_words: int = 50) -> list[dict]:
    """Split pages into overlapping word windows.

    Approximation: 1 word ~ 1.3 tokens. Returns a list of
    ``{"id", "text", "metadata": {"filename", "page"}}``.
    """
    max_words = max(1, int(max_words))
    # The overlap must stay well below the window or the loop would not advance.
    overlap_words = max(0, min(int(overlap_words), max_words // 4))

    chunks = []
    for page in pages:
        words = page["text"].split()
        start = 0
        while start < len(words):
            end = start + max_words
            chunks.append(
                {
                    "id": str(uuid.uuid4()),
                    "text": " ".join(words[start:end]),
                    "metadata": {"filename": page["filename"], "page": page["page"]},
                }
            )
            if end >= len(words):
                break
            start = end - overlap_words
    return chunks
