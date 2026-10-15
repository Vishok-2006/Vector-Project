import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database
from config import get_settings
from embeddings.generate import EmbeddingError
from qdrant_store import VectorStoreError
from security import current_user
from services import llm_service
from services.llm_service import LLM_FAILURE_MESSAGE, LLMGenerationError
from services.rag import get_context

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str = Field(..., max_length=8000)
    chat_id: Optional[str] = Field(default=None, max_length=64)  # None -> start a new chat
    rag_enabled: bool = True


class ChatResponse(BaseModel):
    chat_id: str
    title: str
    answer: str
    context: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_llm_fallback_answer(context: str, error_message: str) -> str:
    cleaned_error = error_message.strip() or LLM_FAILURE_MESSAGE
    has_context = bool(context and context not in {"No relevant context found.", "Error retrieving context."})

    if has_context:
        return f"LLM request failed: {cleaned_error}\n\nRetrieved document context:\n\n{context}"
    return f"LLM request failed: {cleaned_error}"


def _llm_deadline() -> float:
    """Upper bound for one generation incl. retries/backoff, so the request cannot hang."""
    settings = get_settings()
    attempts = settings.llm_max_retries + 1
    return settings.llm_timeout_seconds * attempts + 20.0 * settings.llm_max_retries + 5.0


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, user_id: str = Depends(current_user)):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    chat_id = req.chat_id or str(uuid.uuid4())
    if await asyncio.to_thread(database.chat_exists_for_other_user, user_id, chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")

    existing_chat = await asyncio.to_thread(database.get_chat, user_id, chat_id)
    history = existing_chat["messages"] if existing_chat else []
    title = existing_chat["title"] if existing_chat else "New Chat"

    # 1. Retrieve context from this user's documents (if RAG is enabled)
    context = ""
    retrieval_error: str | None = None
    if req.rag_enabled:
        try:
            context = await asyncio.to_thread(get_context, query, user_id)
        except (EmbeddingError, VectorStoreError) as exc:
            logger.error("RAG context retrieval failed: %s", exc)
            retrieval_error = str(exc)
            context = "Error retrieving context."
        except Exception as exc:
            logger.exception("Unexpected RAG retrieval failure")
            retrieval_error = str(exc)
            context = "Error retrieving context."

    # 2. Generate the answer
    llm_failed = False
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(llm_service.generate_answer, query, context, history),
            timeout=_llm_deadline(),
        )
    except asyncio.TimeoutError:
        llm_failed = True
        logger.error("LLM generation timed out for chat_id=%s", chat_id)
        answer = _build_llm_fallback_answer(context, f"Timed out after {get_settings().llm_timeout_seconds:.0f} seconds.")
    except LLMGenerationError as exc:
        llm_failed = True
        logger.warning("Returning fallback answer for chat_id=%s because the LLM failed.", chat_id)
        answer = _build_llm_fallback_answer(context, str(exc))
    except Exception as exc:
        llm_failed = True
        logger.exception("Unexpected LLM pipeline error for chat_id=%s", chat_id)
        answer = _build_llm_fallback_answer(context, str(exc))

    if retrieval_error and not llm_failed:
        answer += (
            "\n\nNote: searching your documents failed, so this answer is not grounded in them "
            f"({retrieval_error})"
        )

    # 3. Title for new chats (skip the extra LLM call if the LLM is already failing)
    if not existing_chat:
        if llm_failed:
            title = query[:30] + "..." if len(query) > 30 else query
        else:
            title = await asyncio.to_thread(llm_service.generate_title, query)

    # 4. Persist
    new_messages = history + [
        {"role": "user", "content": query, "timestamp": _now()},
        {"role": "assistant", "content": answer, "timestamp": _now()},
    ]
    await asyncio.to_thread(database.save_chat, user_id, chat_id, title, new_messages)

    return ChatResponse(chat_id=chat_id, title=title, answer=answer, context=context if req.rag_enabled else None)


@router.get("/test-llm")
async def test_llm(prompt: str = "Hello", user_id: str = Depends(current_user)):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(llm_service.test_llm_connection, prompt[:500]), timeout=_llm_deadline()
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="LLM request timed out.") from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/chats")
def list_chats(user_id: str = Depends(current_user)):
    return database.get_all_chats(user_id)


@router.get("/chat/{chat_id}")
def fetch_chat(chat_id: str, user_id: str = Depends(current_user)):
    chat = database.get_chat(user_id, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.delete("/chat/{chat_id}")
def remove_chat(chat_id: str, user_id: str = Depends(current_user)):
    if not database.delete_chat(user_id, chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "success"}
