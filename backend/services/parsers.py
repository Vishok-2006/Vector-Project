import fitz # PyMuPDF
import uuid

def extract_text_from_pdf(file_bytes, filename):
    """
    Extracts text page by page from raw bytes.
    Returns: list of dicts {"page": int, "text": str, "filename": str}
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text").strip()
        if text:
            # Clean null bytes
            text = text.replace("\x00", "")
            pages.append({
                "page": page_num + 1,
                "text": text,
                "filename": filename
            })
    return pages

def chunk_text(pages, max_words=500, overlap_words=50):
    """
    Chunks text. Approximation: 1 word ~ 1.3 tokens. 
    500 words is ~650 tokens.
    Returns: list of dicts {"id", "text", "metadata": {"filename", "page"}}
    """
    chunks = []
    for page in pages:
        words = page["text"].split()
        start = 0
        while start < len(words):
            end = start + max_words
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": chunk_text,
                "metadata": {
                    "filename": page["filename"],
                    "page": page["page"]
                }
            })
            if end >= len(words):
                break
            start = end - overlap_words 
    return chunks
