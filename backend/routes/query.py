import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from services.gemini_service import (
    GEMINI_FAILURE_MESSAGE,
    GeminiGenerationError,
    generate_answer,
    generate_title
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
    try:
        answer = generate_answer(query, context, history)
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        answer = GEMINI_FAILURE_MESSAGE
        if context and context != "No relevant context found.":
            answer = f"I couldn't reach the AI, but I found this in the documents:\n\n{context}"

    # 3. Handle Title Generation for new chats
    if not existing_chat:
        title = generate_title(query)

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
