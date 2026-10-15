"""Per-browser identity used to isolate every user's documents, vectors and chats.

How it works
------------
The first time a browser talks to the API we mint a random user id and hand it
back in an HMAC-signed, HttpOnly cookie. Every subsequent request is verified
against the signature, so a client cannot invent or tamper with a user id to
read somebody else's data. All database rows and every Qdrant query are scoped
to that id.

This is *isolation*, not account login: whoever holds the cookie owns the data.
To restrict who can reach a deployment at all, enable the optional HTTP Basic
auth gate in the reverse proxy (``BASIC_AUTH_USER`` / ``BASIC_AUTH_PASSWORD``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import Request, Response

from config import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "vectora_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year


@lru_cache(maxsize=1)
def _secret() -> bytes:
    """Return the HMAC key: SESSION_SECRET if set, else a key persisted on disk.

    Persisting the generated key in the data directory keeps cookies valid across
    container restarts without forcing operators to configure anything.
    """
    settings = get_settings()
    if settings.session_secret:
        return settings.session_secret.encode()

    key_file: Path = settings.data_dir / "session_secret"
    try:
        if key_file.exists():
            existing = key_file.read_text().strip()
            if existing:
                return existing.encode()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_urlsafe(48)
        # 0600: only the app user may read it.
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(generated)
        logger.info("Generated a new session signing key at %s", key_file)
        return generated.encode()
    except OSError:
        logger.warning(
            "Could not persist a session key in %s; using an ephemeral key. "
            "Sessions will reset on restart. Set SESSION_SECRET to avoid this.",
            settings.data_dir,
        )
        return secrets.token_urlsafe(48).encode()


def reset_secret_cache() -> None:
    _secret.cache_clear()


def _sign(user_id: str) -> str:
    digest = hmac.new(_secret(), user_id.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def make_token(user_id: str) -> str:
    return f"{user_id}.{_sign(user_id)}"


def verify_token(token: str | None) -> str | None:
    """Return the user id if *token* carries a valid signature, else ``None``."""
    if not token or "." not in token:
        return None
    user_id, _, signature = token.partition(".")
    if not user_id or len(user_id) > 64:
        return None
    if not hmac.compare_digest(signature, _sign(user_id)):
        return None
    return user_id


def _cookie_should_be_secure(request: Request) -> bool:
    mode = get_settings().cookie_secure
    if mode == "true":
        return True
    if mode == "false":
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


def current_user(request: Request, response: Response) -> str:
    """FastAPI dependency: the verified user id, minting a session when missing."""
    user_id = verify_token(request.cookies.get(COOKIE_NAME))
    if user_id:
        return user_id

    user_id = uuid.uuid4().hex
    response.set_cookie(
        COOKIE_NAME,
        make_token(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_cookie_should_be_secure(request),
        path="/",
    )
    return user_id
