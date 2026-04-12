from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import time
import google.generativeai as genai
import traceback
from dotenv import load_dotenv

from embeddings.generate import get_query_embedding
from endee_client import search_similar

router = APIRouter()

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    try:
        genai.configure(api_key=api_key)
    except Exception:
        print("[WARN] Failed to configure Gemini SDK during startup.")

DEFAULT_MODELS = ["gemini-1.5-flash-latest", "gemini-1.0-pro"]

class Message(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    query: str
    history: Optional[List[Message]] = None

class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    confidence: str
    status: str
    context_used: bool


def _extract_text_from_response(response):
    if response is None:
        return None

    if hasattr(response, "text") and response.text:
        return response.text

    if isinstance(response, dict):
        if "output" in response:
            output = response["output"]
            if isinstance(output, list) and output:
                first = output[0]
                if isinstance(first, dict) and "content" in first:
                    return first["content"]
        if "candidates" in response:
            candidates = response["candidates"]
            if isinstance(candidates, list) and candidates:
                first = candidates[0]
                if isinstance(first, dict) and "content" in first:
                    return first["content"]
        if "content" in response and isinstance(response["content"], str):
            return response["content"]

    if isinstance(response, str):
        return response

    return None


def _list_available_models():
    try:
        if hasattr(genai, "list_models"):
            models = genai.list_models()
            if isinstance(models, dict):
                raw = models.get("models", models.get("data", []))
            else:
                raw = models

            names = []
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and "name" in item:
                        names.append(item["name"])
                    elif isinstance(item, str):
                        names.append(item)
            return [name for name in names if isinstance(name, str)]
    except Exception:
        print("[WARN] genai.list_models() failed.")
        print(traceback.format_exc())
    return []


def _select_model_candidates():
    available = _list_available_models()
    if available:
        print(f"[DEBUG] Gemini reported {len(available)} available models.")
        for candidate in DEFAULT_MODELS:
            if candidate in available:
                print(f"[DEBUG] Selected model from available models: {candidate}")
                return [candidate]
        found = [name for name in available if name.startswith("gemini-")]
        if found:
            print(f"[DEBUG] No preferred model found; using first available Gemini model: {found[0]}")
            return found[:2]
    return DEFAULT_MODELS


def _invoke_gemini(prompt: str, model_name: str, retries: int = 2):
    for attempt in range(1, retries + 1):
        try:
            print(f"[DEBUG] Gemini attempt {attempt} for model {model_name}")
            if hasattr(genai, "GenerativeModel"):
                model = genai.GenerativeModel(model_name)
                if hasattr(model, "generate_content"):
                    return model.generate_content(prompt)
                if hasattr(model, "generate_text"):
                    return model.generate_text(prompt)
            if hasattr(genai, "generate_text"):
                return genai.generate_text(model=model_name, prompt=prompt)
            if hasattr(genai, "generate_content"):
                return genai.generate_content(model=model_name, prompt=prompt)
            raise RuntimeError("Unsupported Gemini SDK interface")
        except Exception as error:
            print(f"[WARN] Gemini call failed on model {model_name} attempt {attempt}: {type(error).__name__}: {error}")
            print(traceback.format_exc())
            if attempt == retries:
                raise
    return None


def _generate_with_fallback(prompt: str):
    model_candidates = _select_model_candidates()
    last_error = None
    for model_name in model_candidates:
        try:
            return _invoke_gemini(prompt, model_name)
        except Exception as error:
            last_error = error
            continue
    if last_error:
        raise last_error
    raise RuntimeError("No valid Gemini models available.")


def _summarize_sources(sources: List[dict]):
    if not sources:
        return "LLM unavailable"
    pieces = []
    for src in sources:
        preview = src["text"][:100].replace("\n", " ")
        pieces.append(f"{src['filename']} page {src['page']}: {preview}")
    return "LLM unavailable; source preview: " + " | ".join(pieces)


@router.post("/query", response_model=QueryResponse)
def query_agentic_rag(req: QueryRequest):
    current_key = os.getenv("GEMINI_API_KEY")
    if not current_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on server.")

    if req.history is None:
        req.history = []

    try:
        genai.configure(api_key=current_key)

        print(f"[DEBUG] Generating embedding for query: {req.query}")
        embed_start = time.perf_counter()
        query_vector = get_query_embedding(req.query)
        embed_end = time.perf_counter()
        print(f"[DEBUG] Embedding completed in {embed_end - embed_start:.3f}s")

        print(f"[DEBUG] Searching Endee DB for top 15 chunks...")
        search_start = time.perf_counter()
        results = search_similar(query_vector, top_k=15)
        search_end = time.perf_counter()
        print(f"[DEBUG] Search completed in {search_end - search_start:.3f}s")

        sources = []
        for r in results:
            score = r.get("score", r.get("similarity", 0.0))
            meta = r.get("meta", {})
            if score is None:
                score = 0.0
            if float(score) < 0.3:
                continue

            text = meta.get("text", "")
            if not text:
                continue

            sources.append({
                "text": text,
                "filename": meta.get("filename", "unknown"),
                "page": meta.get("page", 0),
                "score": round(float(score), 4),
            })

        print(f"[DEBUG] Retrieved {len(results)} candidate chunks; {len(sources)} passed score filter (>=0.3).")
        if len(sources) < 2:
            print("[WARN] Weak retrieval: fewer than 2 relevant chunks were found.")

        for idx, src in enumerate(sources):
            preview = src["text"][:100].replace("\n", " ")
            print(f"[DEBUG] Chunk {idx+1}: {src['filename']} - Page {src['page']} (Score: {src['score']}) Preview: {preview}")

        if not sources:
            return QueryResponse(
                answer="No relevant data found in documents",
                sources=[],
                confidence="low",
                status="no_data",
                context_used=False,
            )

        context = "\n---\n".join(
            f"Document: {src['filename']}, Page {src['page']}\n{src['text']}"
            for src in sources
        )

        prompt = f"""You are an AI research assistant.
Answer ONLY using the provided context.
Do not use external knowledge.

If the answer is not found, respond exactly:
'Not found in documents.'

Provide clear, structured answers.

Context:
{context}

Question: {req.query}
"""

        print(f"[DEBUG] --- FINAL PROMPT SENT TO LLM ---\n{prompt}\n--------------------------------------")

        llm_start = time.perf_counter()
        try:
            response = _generate_with_fallback(prompt)
            answer_text = _extract_text_from_response(response)
            llm_end = time.perf_counter()
            print(f"[DEBUG] LLM completed in {llm_end - llm_start:.3f}s")
            if not answer_text:
                raise RuntimeError("Gemini returned no text")
            return QueryResponse(
                answer=answer_text,
                sources=sources,
                confidence="high",
                status="success",
                context_used=True,
            )
        except Exception:
            llm_end = time.perf_counter()
            print(f"[ERROR] Gemini failed after {llm_end - llm_start:.3f}s")
            print(traceback.format_exc())
            fallback_answer = _summarize_sources(sources)
            return QueryResponse(
                answer=fallback_answer,
                sources=sources,
                confidence="low",
                status="fallback",
                context_used=True,
            )
    except Exception:
        print("[ERROR] /api/query failed!")
        print(traceback.format_exc())
        return QueryResponse(
            answer="LLM unavailable",
            sources=[],
            confidence="low",
            status="fallback",
            context_used=True,
        )
