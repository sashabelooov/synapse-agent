"""Conversation persistence.

Save and load chat history to disk as JSON so a conversation survives a restart.
This works because every adapter's build_assistant_message() returns plain
JSON-serializable dicts (not raw provider objects).
"""

import json
import time
from pathlib import Path

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"


def _ensure_dir() -> None:
    SESSIONS_DIR.mkdir(exist_ok=True)


def save_session(messages: list[dict], name: str | None = None) -> str:
    """Save messages to sessions/<name>.json. Returns the file path."""
    _ensure_dir()
    name = name or f"session_{int(time.time())}"
    if not name.endswith(".json"):
        name += ".json"
    path = SESSIONS_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, default=str)
    return str(path)


def load_session(name: str) -> list[dict]:
    """Load messages from sessions/<name>.json."""
    if not name.endswith(".json"):
        name += ".json"
    path = SESSIONS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"No session named '{name}' in {SESSIONS_DIR}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_sessions() -> list[str]:
    """List saved session names (without the .json suffix)."""
    if not SESSIONS_DIR.exists():
        return []
    return sorted(p.stem for p in SESSIONS_DIR.glob("*.json"))
