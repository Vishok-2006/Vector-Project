"""Retrieval: embed the question, search Qdrant (scoped to the user), build the prompt context."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

from config import get_settings
from embeddings.generate import get_query_embedding
from qdrant_store import get_store

logger = logging.getLogger(__name__)

MAX_CONTEXT_WORDS = 1800
NEAR_DUPLICATE_THRESHOLD = 0.88


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _normalize_results(results: list[dict] | None, min_score: float | None = None) -> list[dict]:
    """Drop low-similarity / empty hits and return them best-first."""
    threshold = get_settings().rag_min_score if min_score is None else min_score
    normalized = []

    for item in results or []:
        if not isinstance(item, dict):
            continue
        score = _safe_float(item.get("score", 0.0))
        if score < threshold:
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        normalized.append(
            {
                "filename": str(item.get("filename", "unknown")),
                "page": item.get("page", 0),
                "score": round(score, 4),
                "text": text,
            }
        )

    return sorted(normalized, key=lambda item: item["score"], reverse=True)


def _is_near_duplicate(candidate: dict, selected: list[dict]) -> bool:
    candidate_text = _normalize_text(candidate["text"])
    if not candidate_text:
        return True

    for chunk in selected:
        if candidate["filename"] != chunk["filename"] or candidate["page"] != chunk["page"]:
            continue

        current_text = _normalize_text(chunk["text"])
        if candidate_text == current_text:
            return True
        if candidate_text in current_text or current_text in candidate_text:
            return True
        if SequenceMatcher(None, candidate_text, current_text).ratio() >= NEAR_DUPLICATE_THRESHOLD:
            return True

    return False


def _dedupe_results(chunks: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    for chunk in chunks:
        if not _is_near_duplicate(chunk, deduped):
            deduped.append(chunk)
    return deduped


def _trim_to_word_limit(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).strip()


def _limit_context(chunks: list[dict], max_context_words: int = MAX_CONTEXT_WORDS) -> list[dict]:
    selected: list[dict] = []
    total_words = 0

    for chunk in chunks:
        word_count = len(chunk["text"].split())

        if not selected and word_count > max_context_words:
            selected.append({**chunk, "text": _trim_to_word_limit(chunk["text"], max_context_words)})
            break

        if total_words + word_count > max_context_words:
            continue

        selected.append(chunk)
        total_words += word_count

    return selected


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant context found."

    blocks = [
        f"[Source {index}] {chunk['filename']} (page {chunk['page']})\n{chunk['text']}"
        for index, chunk in enumerate(chunks, start=1)
    ]
    return "\n\n".join(blocks)


def get_context(question: str, user_id: str, top_k: int | None = None) -> str:
    """Return formatted, de-duplicated, budget-limited context for *question* from this user's documents."""
    settings = get_settings()
    query_vector = get_query_embedding(question)
    results = get_store().search(user_id, query_vector, top_k=top_k or settings.rag_top_k)
    normalized = _normalize_results(results)
    selected = _limit_context(_dedupe_results(normalized))

    logger.info(
        "Retrieved %d hits from Qdrant (%d above score %.2f); kept %d after dedupe/budgeting.",
        len(results),
        len(normalized),
        settings.rag_min_score,
        len(selected),
    )
    return _format_context(selected)
