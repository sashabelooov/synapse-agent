"""Conversation persistence — SQLite backend.

Stores sessions and messages in ~/.synapse/sessions.db.
Supports FTS5 full-text search across all past sessions via search_sessions_db().

The public interface (save_session / load_session / list_sessions) is unchanged
from the JSON version so agent/loop.py requires no updates.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    env = os.environ.get("SYNAPSE_HOME")
    base = Path(env) if env else Path.home() / ".synapse"
    base.mkdir(parents=True, exist_ok=True)
    return base / "sessions.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    ts          TEXT    NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_content(content: Any) -> str:
    """Encode message content to a storable string."""
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def _decode_content(raw: str) -> Any:
    """Decode stored content back to its original type."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, (list, dict)):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_session(messages: list[dict], name: str | None = None) -> str:
    """Save messages to SQLite. Returns the session name."""
    ts = _now()
    session_name = name or f"session-{ts[:19].replace(':', '-').replace('T', '-')}"

    with _connect() as conn:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO sessions(name, created_at, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at",
            (session_name, ts, ts),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE name=?", (session_name,)
        ).fetchone()["id"]

        # Full overwrite — delete existing messages then re-insert.
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        for msg in messages:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, ts) VALUES(?,?,?,?)",
                (session_id, msg.get("role", ""), _encode_content(msg.get("content", "")), ts),
            )
        conn.commit()

    return session_name


def load_session(name: str) -> list[dict]:
    """Load messages by session name. Raises ValueError if not found."""
    with _connect() as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT id FROM sessions WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Session '{name}' not found.")
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
            (row["id"],),
        ).fetchall()

    return [{"role": r["role"], "content": _decode_content(r["content"])} for r in rows]


def list_sessions() -> list[str]:
    """Return all session names, most recently updated first."""
    with _connect() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT name FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [r["name"] for r in rows]


def search_sessions_db(query: str, limit: int = 5) -> list[dict]:
    """Full-text search across all session messages using SQLite FTS5.

    Returns a list of dicts: {session, date, role, excerpt}.
    """
    with _connect() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT s.name, s.updated_at, m.role, m.content
            FROM messages_fts f
            JOIN messages m ON m.id = f.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

    results = []
    for r in rows:
        excerpt = r["content"]
        if len(excerpt) > 200:
            excerpt = excerpt[:200] + "…"
        results.append({
            "session": r["name"],
            "date": r["updated_at"][:10],
            "role": r["role"],
            "excerpt": excerpt,
        })
    return results
