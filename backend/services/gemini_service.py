import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
GEMINI_FAILURE_MESSAGE = "LLM request failed."
PROMPT_TEMPLATE = """You are a helpful assistant answering questions.
If context is provided, prioritize it.
If no context is provided, answer using your general knowledge but mention that no specific documents were found.

Context:
{context}

Question:
{question}

Answer:"""


class GeminiGenerationError(Exception):
    """Raised when Gemini fails to return a valid answer."""


def build_prompt(context: str, question: str) -> str:
    return PROMPT_TEMPLATE.format(context=context, question=question)


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "google":
        return "gemini"
    return normalized


def get_llm_provider() -> str:
    configured_provider = os.getenv("LLM_PROVIDER", "").strip()

    if configured_provider:
        provider = _normalize_provider(configured_provider)
    elif os.getenv("GEMINI_API_KEY", "").strip():
        provider = "gemini"
    elif os.getenv("OPENAI_API_KEY", "").strip():
        provider = "openai"
    else:
        provider = "gemini"

    if provider not in {"gemini", "openai"}:
        raise GeminiGenerationError(
            f"Unsupported LLM_PROVIDER '{provider}'. Use 'gemini' or 'openai'."
        )

    return provider


def get_llm_model() -> str:
    provider = get_llm_provider()
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL


def get_llm_timeout_seconds() -> float:
    raw_timeout = os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS)).strip()

    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise GeminiGenerationError(
            f"Invalid LLM_TIMEOUT_SECONDS '{raw_timeout}'. Use a positive number."
        ) from exc

    if timeout_seconds <= 0:
        raise GeminiGenerationError("LLM_TIMEOUT_SECONDS must be greater than zero.")

    return timeout_seconds


def get_llm_runtime_config() -> dict[str, Any]:
    return {
        "provider": get_llm_provider(),
        "model": get_llm_model(),
        "timeout_seconds": get_llm_timeout_seconds(),
    }


def validate_llm_config() -> dict[str, Any]:
    config = get_llm_runtime_config()

    if config["provider"] == "gemini":
        if not os.getenv("GEMINI_API_KEY", "").strip():
            raise RuntimeError(
                "LLM provider 'gemini' selected but GEMINI_API_KEY is missing. "
                "Set it in backend/.env or the process environment."
            )
    else:
        if OpenAI is None:
            raise RuntimeError(
                "LLM provider 'openai' selected but the 'openai' package is not installed."
            )
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise RuntimeError(
                "LLM provider 'openai' selected but OPENAI_API_KEY is missing. "
                "Set it in backend/.env or the process environment."
            )

    return config


def _configure_gemini_model() -> genai.GenerativeModel:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiGenerationError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(get_llm_model())


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


def _extract_openai_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise GeminiGenerationError("OpenAI returned no choices.")

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)

    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        text_parts = []
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
                continue

            if isinstance(part, dict):
                dict_text = part.get("text")
                if isinstance(dict_text, str) and dict_text.strip():
                    text_parts.append(dict_text.strip())

        if text_parts:
            return "\n".join(text_parts).strip()

    raise GeminiGenerationError("OpenAI response did not contain readable text.")


def _generate_gemini_text(prompt: str, temperature: float, max_output_tokens: int) -> str:
    model = _configure_gemini_model()
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": temperature,
            "top_p": 0.9,
            "max_output_tokens": max_output_tokens,
        },
        request_options={"timeout": get_llm_timeout_seconds()},
    )
    return _sanitize_answer(_extract_response_text(response))


def _generate_openai_text(prompt: str, temperature: float, max_output_tokens: int) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise GeminiGenerationError("OPENAI_API_KEY is not configured.")

    if OpenAI is None:
        raise GeminiGenerationError(
            "OpenAI provider selected but the 'openai' package is not installed."
        )

    client = OpenAI(api_key=api_key, timeout=get_llm_timeout_seconds())
    response = client.chat.completions.create(
        model=get_llm_model(),
        temperature=temperature,
        max_tokens=max_output_tokens,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant answering questions using the provided context.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    return _sanitize_answer(_extract_openai_response_text(response))


def _generate_text(prompt: str, temperature: float = 0.2, max_output_tokens: int = 1024) -> str:
    config = validate_llm_config()

    try:
        if config["provider"] == "openai":
            return _generate_openai_text(prompt, temperature, max_output_tokens)

        return _generate_gemini_text(prompt, temperature, max_output_tokens)
    except Exception as exc:
        logger.exception(
            "LLM request failed. provider=%s model=%s timeout=%ss",
            config["provider"],
            config["model"],
            config["timeout_seconds"],
        )
        raise GeminiGenerationError(
            f"LLM request failed for provider '{config['provider']}' and model '{config['model']}': {exc}"
        ) from exc


def generate_title(message: str) -> str:
    """Generate a short title from the first message."""
    prompt = (
        "Generate a very short title for this chat in at most 5 words. "
        "Return only the title text.\n\n"
        f"Message: {message}"
    )

    try:
        title = _generate_text(prompt, temperature=0.1, max_output_tokens=32)
        return title.replace('"', "").strip()
    except GeminiGenerationError:
        return message[:30] + "..." if len(message) > 30 else message


def generate_answer(question: str, context: str, history: list = None) -> str:
    """
    Generate a clean answer using the configured LLM provider.
    If history is provided, it can be used for context (future improvement).
    Currently simplifies to system prompt + context + question.
    """
    prompt = build_prompt(context=context, question=question)
    return _generate_text(prompt, temperature=0.2, max_output_tokens=1024)


def test_llm_connection(prompt: str = "Hello") -> dict[str, Any]:
    response = _generate_text(prompt, temperature=0.1, max_output_tokens=256)
    config = get_llm_runtime_config()
    return {
        "provider": config["provider"],
        "model": config["model"],
        "timeout_seconds": config["timeout_seconds"],
        "prompt": prompt,
        "response": response,
    }

async def stream_answer(question: str, context: str, history: list = None):
    """Generator for streaming answers."""
    try:
        answer = await asyncio.to_thread(generate_answer, question, context, history)
        yield answer
    except Exception as exc:
        yield f"LLM request failed: {exc}"
