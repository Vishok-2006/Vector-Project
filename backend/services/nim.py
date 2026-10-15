"""Tiny HTTP client for NVIDIA NIM's OpenAI-compatible API.

Chat completions and embeddings are *different models* behind *different
endpoints* (``/chat/completions`` vs ``/embeddings``); this client exposes both
but they are configured and used independently.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 20.0


class NimError(Exception):
    """A NIM call failed. ``str(exc)`` is safe to show to end users (never contains the key)."""

    def __init__(self, message: str, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def _server_detail(response: httpx.Response) -> str:
    """Best-effort extraction of the server's error message."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:300]
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
        for key in ("detail", "message", "error", "title"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value[:300]
            if isinstance(value, list) and value:
                return str(value[0])[:300]
    return str(body)[:300]


def describe_http_error(status: int, detail: str, model: str) -> str:
    detail_suffix = f" Server said: {detail}" if detail else ""
    if status == 401:
        return "NVIDIA NIM rejected the API key (HTTP 401). Check NVIDIA_API_KEY." + detail_suffix
    if status == 403:
        return (
            f"NVIDIA NIM denied access (HTTP 403). The key may not have access to model '{model}'."
            + detail_suffix
        )
    if status in (404, 410):
        reason = "has been retired" if status == 410 else "could not be found"
        return (
            f"NVIDIA NIM model '{model}' {reason} (HTTP {status}). Pick a current model from the NVIDIA "
            "API catalog and set NVIDIA_MODEL (chat) or EMBEDDING_MODEL (embeddings); also check "
            "NVIDIA_BASE_URL." + detail_suffix
        )
    if status in (400, 422):
        return f"NVIDIA NIM rejected the request (HTTP {status})." + detail_suffix
    if status == 429:
        return "NVIDIA NIM rate limit reached (HTTP 429). Wait a moment and retry." + detail_suffix
    if status >= 500:
        return f"NVIDIA NIM service error (HTTP {status}). Try again shortly." + detail_suffix
    return f"NVIDIA NIM returned HTTP {status}." + detail_suffix


class NimClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ plumbing

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        model: str,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise NimError("NVIDIA_API_KEY is not configured.", status=401)

        url = f"{self.base_url}{path}"
        retries = self.max_retries if max_retries is None else max_retries
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: NimError | None = None

        for attempt in range(retries + 1):
            delay = self.backoff_base * (2**attempt) + random.uniform(0, 0.25 * self.backoff_base)
            try:
                response = self._http.post(url, json=payload, headers=headers, timeout=timeout or self.timeout)
            except httpx.TimeoutException:
                last_error = NimError(
                    f"NVIDIA NIM did not answer within {(timeout or self.timeout):.0f} seconds.",
                    retryable=True,
                )
            except httpx.HTTPError as exc:
                last_error = NimError(
                    f"Could not connect to NVIDIA NIM at {self.base_url}: {type(exc).__name__}", retryable=True
                )
            else:
                if response.status_code < 400:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        raise NimError("NVIDIA NIM returned a response that was not valid JSON.") from exc
                    if not isinstance(body, dict):
                        raise NimError("NVIDIA NIM returned an unexpected response shape.")
                    return body

                status = response.status_code
                retryable = status in RETRYABLE_STATUS
                last_error = NimError(
                    describe_http_error(status, _server_detail(response), model), status=status, retryable=retryable
                )
                retry_after = response.headers.get("retry-after", "")
                if retry_after.replace(".", "", 1).isdigit():
                    delay = max(delay, float(retry_after))

            if not last_error.retryable or attempt >= retries:
                break
            delay = min(delay, MAX_BACKOFF_SECONDS)
            logger.warning(
                "NIM %s failed (%s); retry %d/%d in %.1fs", path, last_error, attempt + 1, retries, delay
            )
            time.sleep(delay)

        assert last_error is not None
        raise last_error

    # --------------------------------------------------------------------- chat

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> str:
        body = self._post(
            "/chat/completions",
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.9,
                "max_tokens": max_tokens,
                "stream": False,
            },
            model=model,
            timeout=timeout,
            max_retries=max_retries,
        )
        choices = body.get("choices") or []
        if not choices:
            raise NimError("NVIDIA NIM returned no completion choices.")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):  # some servers return structured parts
            content = "\n".join(
                part.get("text", "") for part in content if isinstance(part, dict) and part.get("text")
            )
        if not isinstance(content, str) or not content.strip():
            raise NimError("NVIDIA NIM returned an empty answer.")
        return content

    # --------------------------------------------------------------- embeddings

    def embeddings(
        self,
        model: str,
        inputs: list[str],
        input_type: str | None = None,
        truncate: str | None = "END",
    ) -> list[list[float]]:
        """Embed *inputs*. ``input_type`` is ``"passage"`` (indexing) or ``"query"`` (search)
        for asymmetric retrieval models such as ``nvidia/nv-embedqa-e5-v5``."""
        if not inputs:
            return []
        payload: dict[str, Any] = {"model": model, "input": inputs, "encoding_format": "float"}
        if input_type:
            payload["input_type"] = input_type
            if truncate:
                payload["truncate"] = truncate
        body = self._post("/embeddings", payload, model=model)
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(inputs):
            raise NimError(
                f"NVIDIA NIM returned {len(data) if isinstance(data, list) else 0} embeddings "
                f"for {len(inputs)} inputs."
            )
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") for item in ordered]
        if any(not isinstance(v, list) or not v for v in vectors):
            raise NimError("NVIDIA NIM returned a malformed embedding.")
        return vectors
