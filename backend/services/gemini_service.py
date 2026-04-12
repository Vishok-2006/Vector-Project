import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_FAILURE_MESSAGE = "⚠️ Unable to generate answer. Please try again."
PROMPT_TEMPLATE = """You are a helpful assistant answering questions.
If context is provided, prioritize it.
If no context is provided, answer using your general knowledge but mention that no specific documents were found.

Context:
{context}

Question:
{question}

Answer:"""

def generate_title(message: str) -> str:
    """Generate a short title from the first message."""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"Generate a very short (max 5 words) title for a chat that starts with: '{message}'. Return only the title text."
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception:
        return message[:30] + "..." if len(message) > 30 else message


class GeminiGenerationError(Exception):
    """Raised when Gemini fails to return a valid answer."""


def build_prompt(context: str, question: str) -> str:
    return PROMPT_TEMPLATE.format(context=context, question=question)


def _configure_model() -> genai.GenerativeModel:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiGenerationError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def _extract_response_text(response) -> str:
    if response is None:
        raise GeminiGenerationError("Gemini returned no response.")

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        first_candidate = candidates[0]
        content = getattr(first_candidate, "content", None)
        parts = getattr(content, "parts", None) or []

        text_parts = []
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

        if text_parts:
            return "\n".join(text_parts).strip()

    try:
        text = response.text
    except Exception as exc:  # pragma: no cover - depends on Gemini SDK response state
        raise GeminiGenerationError("Gemini response did not contain readable text.") from exc

    if isinstance(text, str) and text.strip():
        return text.strip()

    raise GeminiGenerationError("Gemini returned an empty answer.")


def _sanitize_answer(answer: str) -> str:
    cleaned = answer.strip()

    for prefix in ("## Answer:", "Answer:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].lstrip()

    cleaned_lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]
    cleaned = "\n".join(cleaned_lines).strip()

    if not cleaned:
        raise GeminiGenerationError("Gemini returned a blank answer after sanitization.")

    return cleaned


def generate_answer(question: str, context: str, history: list = None) -> str:
    """
    Generate a clean answer using Gemini. 
    If history is provided, it can be used for context (future improvement).
    Currently simplifies to system prompt + context + question.
    """
    prompt = build_prompt(context=context, question=question)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        logger.error("GEMINI_API_KEY is not configured.")
        raise GeminiGenerationError("Gemini generation failed.")

    genai.configure(api_key=api_key)

    model_candidates = (
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    )

    last_error = None
    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name)
            
            # Simple approach: append history to message if needed
            # For now, we follow the RAG pattern but keep history awareness
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "max_output_tokens": 1024,
                },
            )

            answer = _sanitize_answer(_extract_response_text(response))
            if not answer:
                raise GeminiGenerationError("Gemini returned an empty answer.")

            return answer
        except Exception as exc:
            last_error = exc
            continue

    if context:
        return f"I couldn't reach the AI model, but I found this relevant information in your documents:\n\n{context}"
    
    raise GeminiGenerationError("Gemini generation failed.") from last_error

async def stream_answer(question: str, context: str, history: list = None):
    """Generator for streaming answers."""
    prompt = build_prompt(context=context, question=question)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        yield "Error: GEMINI_API_KEY not configured."
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    try:
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        if context:
            yield f"I reached an error with the AI, but here is the document context:\n\n{context}"
        else:
            yield f"Error: {str(e)}"
