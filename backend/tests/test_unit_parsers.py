import pytest

from services.parsers import PdfError, chunk_text, extract_text_from_pdf


def _pages(n_words, page=1, name="a.pdf"):
    return [{"page": page, "text": " ".join(f"w{i}" for i in range(n_words)), "filename": name}]


def test_chunking_overlaps_and_covers_all_words():
    chunks = chunk_text(_pages(1000), max_words=400, overlap_words=50)
    assert [len(c["text"].split()) for c in chunks] == [400, 400, 300]
    assert chunks[0]["text"].split()[-50:] == chunks[1]["text"].split()[:50]
    assert chunks[-1]["text"].split()[-1] == "w999"
    assert all(c["metadata"] == {"filename": "a.pdf", "page": 1} for c in chunks)
    assert len({c["id"] for c in chunks}) == len(chunks)


def test_chunking_always_terminates_when_overlap_exceeds_window():
    chunks = chunk_text(_pages(300), max_words=50, overlap_words=500)
    assert 1 < len(chunks) < 100


def test_chunk_of_short_page_is_single():
    assert len(chunk_text(_pages(10), max_words=500)) == 1


def test_extract_roundtrip(make_pdf):
    pdf = make_pdf(["Alpha beta gamma", "Second page text"])
    pages = extract_text_from_pdf(pdf, "x.pdf")
    assert [p["page"] for p in pages] == [1, 2]
    assert "Alpha beta gamma" in pages[0]["text"]
    assert pages[0]["filename"] == "x.pdf"


def test_non_pdf_and_corrupt_pdf_are_rejected_cleanly():
    with pytest.raises(PdfError):
        extract_text_from_pdf(b"hello world", "x.pdf")
    with pytest.raises(PdfError):
        extract_text_from_pdf(b"%PDF-1.4 garbage garbage", "x.pdf")


def test_blank_pdf_returns_no_pages(make_pdf):
    assert extract_text_from_pdf(make_pdf([""]), "blank.pdf") == []
