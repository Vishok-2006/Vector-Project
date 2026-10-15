"""SQLite persistence for chats and the document registry (vectors live in Qdrant).

Every row belongs to a ``user_id``; every query filters on it, which is what keeps
users' data separate.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config import get_settings

logger = logging.getLogger(__name__)

_ISO_NOW = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    """Create tables and upgrade databases created by pre-2.0 releases.

    Rows written before user isolation existed are kept (never dropped) but are
    tagged with an empty user id, so no user can see them.
    """
    with _connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                title TEXT,
                messages TEXT,
                created_at TEXT DEFAULT ({_ISO_NOW}),
                updated_at TEXT DEFAULT ({_ISO_NOW})
            )
            """
        )
        chat_cols = _columns(conn, "chats")
        if "user_id" not in chat_cols:
            conn.execute("ALTER TABLE chats ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        if "updated_at" not in chat_cols:
            conn.execute("ALTER TABLE chats ADD COLUMN updated_at TEXT")
            conn.execute("UPDATE chats SET updated_at = created_at WHERE updated_at IS NULL")

        existing_docs = _columns(conn, "documents")
        if existing_docs and "user_id" not in existing_docs:
            # Old schema had a global UNIQUE(filename); SQLite cannot alter that, so
            # park the old table (data preserved) and create the per-user one.
            conn.execute("ALTER TABLE documents RENAME TO documents_legacy")
            logger.warning("Renamed pre-2.0 'documents' table to 'documents_legacy'.")

        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                status TEXT,
                chunks INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT ({_ISO_NOW}),
                UNIQUE (user_id, filename)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_user ON chats (user_id, updated_at)")


# --------------------------------------------------------------------------- chats


def save_chat(user_id: str, chat_id: str, title: str, messages: list[dict]) -> None:
    with _connect() as conn:
        owner = conn.execute("SELECT user_id FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
        if owner is not None and owner["user_id"] != user_id:
            raise PermissionError("chat belongs to another user")
        conn.execute(
            f"""
            INSERT INTO chats (chat_id, user_id, title, messages)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                messages = excluded.messages,
                updated_at = {_ISO_NOW}
            """,
            (chat_id, user_id, title, json.dumps(messages)),
        )


def get_chat(user_id: str, chat_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT chat_id, title, messages, created_at, updated_at FROM chats "
            "WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
    if not row:
        return None
    chat = dict(row)
    chat["messages"] = json.loads(chat["messages"] or "[]")
    return chat


def chat_exists_for_other_user(user_id: str, chat_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT user_id FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
    return row is not None and row["user_id"] != user_id


def get_all_chats(user_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT chat_id, title, created_at FROM chats WHERE user_id = ? "
            "ORDER BY updated_at DESC, created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_chat(user_id: str, chat_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM chats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        return cursor.rowcount > 0


# ----------------------------------------------------------------------- documents


def add_document(user_id: str, filename: str, status: str = "success", chunks: int = 0) -> None:
    with _connect() as conn:
        conn.execute(
            f"""
            INSERT INTO documents (user_id, filename, status, chunks)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, filename) DO UPDATE SET
                status = excluded.status,
                chunks = excluded.chunks,
                created_at = {_ISO_NOW}
            """,
            (user_id, filename, status, chunks),
        )


def get_all_documents(user_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, filename, status, chunks, created_at FROM documents "
            "WHERE user_id = ? ORDER BY created_at DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_document_by_filename(user_id: str, filename: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, filename, status, chunks, created_at FROM documents "
            "WHERE user_id = ? AND filename = ?",
            (user_id, filename),
        ).fetchone()
    return dict(row) if row else None


def get_document(user_id: str, document_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, filename, status, chunks, created_at FROM documents "
            "WHERE id = ? AND user_id = ?",
            (document_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def delete_document(user_id: str, document_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)
        )
        return cursor.rowcount > 0


def delete_all_documents(user_id: str) -> int:
    with _connect() as conn:
        return conn.execute("DELETE FROM documents WHERE user_id = ?", (user_id,)).rowcount
