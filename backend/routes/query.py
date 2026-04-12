import asyncio
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from services.gemini_service import (
    GEMINI_FAILURE_MESSAGE,
    GeminiGenerationError,
    generate_answer,
    generate_title,
    get_llm_timeout_seconds,
    test_llm_connection,
)
from services.rag import get_context
from database import save_chat, get_chat, get_all_chats, delete_chat

router = APIRouter()
logger = logging.getLogger(__name__)

class Message(BaseModel):
    role: str # 'user' or 'assistant'
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    query: str
    chat_id: Optional[str] = None # If None, create new chat
    rag_enabled: bool = True

class ChatResponse(BaseModel):
    chat_id: str
    title: str
    answer: str
    context: Optional[str] = None


def _build_llm_fallback_answer(context: str, error_message: str) -> str:
    cleaned_error = error_message.strip() or GEMINI_FAILURE_MESSAGE
    has_context = bool(context and context not in {"No relevant context found.", "Error retrieving context."})

    if has_context:
        return (
            f"LLM request failed: {cleaned_error}\n\n"
            "Retrieved document context:\n\n"
            f"{context}"
        )

    return f"LLM request failed: {cleaned_error}"

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    chat_id = req.chat_id or str(uuid.uuid4())
    existing_chat = get_chat(chat_id)
    
    history = existing_chat['messages'] if existing_chat else []
    title = existing_chat['title'] if existing_chat else "New Chat"

    # 1. Get Context if RAG enabled
    context = ""
    if req.rag_enabled:
        try:
            context = get_context(query)
        except Exception as e:
            logger.error(f"RAG context retrieval failed: {e}")
            context = "Error retrieving context."

    # 2. Generate Answer
    llm_timeout_seconds = get_llm_timeout_seconds()
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(generate_answer, query, context, history),
            timeout=llm_timeout_seconds + 5,
        )
    except asyncio.TimeoutError:
        timeout_message = f"Timed out after {llm_timeout_seconds:.0f} seconds."
        logger.exception("LLM generation timed out for chat_id=%s", chat_id)
        answer = _build_llm_fallback_answer(context, timeout_message)
    except GeminiGenerationError as exc:
        logger.warning("Returning fallback answer for chat_id=%s because the LLM failed.", chat_id)
        answer = _build_llm_fallback_answer(context, str(exc))
    except Exception as exc:
        logger.exception("Unexpected LLM pipeline error for chat_id=%s", chat_id)
        answer = _build_llm_fallback_answer(context, str(exc))

    # 3. Handle Title Generation for new chats
    if not existing_chat:
        title = await asyncio.to_thread(generate_title, query)

    # 4. Save to DB
    new_messages = history + [
        {"role": "user", "content": query, "timestamp": datetime.now().isoformat()},
        {"role": "assistant", "content": answer, "timestamp": datetime.now().isoformat()}
    ]
    save_chat(chat_id, title, new_messages)

    return ChatResponse(
        chat_id=chat_id,
        title=title,
        answer=answer,
        context=context if req.rag_enabled else None
    )


@router.get("/test-llm")
async def test_llm(prompt: str = "Hello"):
    llm_timeout_seconds = get_llm_timeout_seconds()

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(test_llm_connection, prompt),
            timeout=llm_timeout_seconds + 5,
        )
    except asyncio.TimeoutError as exc:
        logger.exception("/test-llm timed out")
        raise HTTPException(
            status_code=504,
            detail=f"LLM request timed out after {llm_timeout_seconds:.0f} seconds.",
        ) from exc
    except GeminiGenerationError as exc:
        logger.exception("/test-llm failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected /test-llm failure")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.get("/chats")
async def list_chats():
    return get_all_chats()

@router.get("/chat/{chat_id}")
async def fetch_chat(chat_id: str):
    chat = get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@router.delete("/chat/{chat_id}")
async def remove_chat(chat_id: str):
    success = delete_chat(chat_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "success"}
