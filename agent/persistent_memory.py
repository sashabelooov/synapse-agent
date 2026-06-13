"""Persistent cross-session memory — two flat files on disk.

  ~/.synapse/MEMORY.md  — agent notes and decisions  (max 2200 chars)
  ~/.synapse/USER.md    — user profile and preferences (max 1375 chars)

Entries are delimited by § (section sign U+00A7).

A **frozen snapshot** is captured once at session start and injected into
the system prompt. It never changes mid-session — this keeps the LLM prefix
cache stable across all turns.

Live state (what the memory tool writes) is persisted atomically to disk so
it is available to future sessions, but does NOT alter the frozen snapshot
already in the system prompt.

Safety properties (adapted from NousResearch/hermes-agent):
- Atomic writes: write to .tmp → rename; readers always see complete files.
- Drift detection: if the file is externally modified after the snapshot,
  a timestamped backup is created before any write.
- Injection scanning: entries are checked for prompt-injection patterns
  before entering the system prompt.
- Deduplication: identical entries are silently discarded on add.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

ENTRY_SEP = "§"
MEMORY_MAX_CHARS = 2200
USER_MAX_CHARS = 1375

# Patterns that indicate prompt-injection attempts.
_THREAT_RE = re.compile(
    r"ignore\s+(previous|all|prior)\s+instructions?"
    r"|you\s+are\s+now\s+a"
    r"|disregard\s+(all|previous|prior)"
    r"|forget\s+(everything|all|your|previous)"
    r"|new\s+instructions?:"
    r"|override\s+(your|the)\s+(instructions?|settings?)"
    r"|<\s*/?system\s*>",
    re.IGNORECASE,
)


def _synapse_home() -> Path:
    env = os.environ.get("SYNAPSE_HOME")
    return Path(env) if env else Path.home() / ".synapse"


def _is_safe(text: str) -> bool:
    return not _THREAT_RE.search(text)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)


def _parse_entries(text: str) -> list[str]:
    return [e.strip() for e in text.split(ENTRY_SEP) if e.strip()]


def _serialize_entries(entries: list[str]) -> str:
    return ("\n" + ENTRY_SEP + "\n").join(entries)


class _Store:
    """One §-delimited flat-file memory store."""

    def __init__(self, path: Path, max_chars: int) -> None:
        self._path = path
        self._max = max_chars
        self._entries: list[str] = []
        self._snapshot_mtime: float = 0.0
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        if self._path.exists():
            raw = self._path.read_text(encoding="utf-8")
            self._entries = [e for e in _parse_entries(raw) if _is_safe(e)]
            self._snapshot_mtime = self._path.stat().st_mtime
        else:
            self._entries = []
            self._snapshot_mtime = 0.0

    @property
    def snapshot_entries(self) -> list[str]:
        return list(self._entries)

    def prompt_block(self, header: str) -> str:
        if not self._entries:
            return ""
        body = "\n".join(f"- {e}" for e in self._entries)
        return f"--- {header} ---\n{body}\n--- END {header} ---"

    def _total_chars(self) -> int:
        return sum(len(e) for e in self._entries)

    def _check_drift(self) -> None:
        if not self._path.exists():
            return
        current_mtime = self._path.stat().st_mtime
        if current_mtime != self._snapshot_mtime:
            ts = int(time.time())
            backup = self._path.with_suffix(f".bak.{ts}")
            shutil.copy2(self._path, backup)

    def _persist(self) -> None:
        self._check_drift()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path, _serialize_entries(self._entries))
        self._snapshot_mtime = self._path.stat().st_mtime

    def add(self, entry: str) -> str:
        entry = entry.strip()
        if not entry:
            return "Error: entry is empty."
        if not _is_safe(entry):
            return "Error: entry contains disallowed content."
        if entry in self._entries:
            return "Already present — skipped (deduplicated)."
        if self._total_chars() + len(entry) > self._max:
            return (
                f"Error: store is full ({self._total_chars()}/{self._max} chars). "
                "Remove old entries first."
            )
        self._entries.append(entry)
        self._persist()
        return f"Added. ({self._total_chars()}/{self._max} chars used)"

    def replace(self, old_text: str, new_text: str) -> str:
        new_text = new_text.strip()
        if not _is_safe(new_text):
            return "Error: new text contains disallowed content."
        idx = next((i for i, e in enumerate(self._entries) if old_text in e), None)
        if idx is None:
            return f"Error: no entry contains '{old_text}'."
        self._entries[idx] = new_text
        self._persist()
        return "Replaced."

    def remove(self, substring: str) -> str:
        before = len(self._entries)
        self._entries = [e for e in self._entries if substring not in e]
        removed = before - len(self._entries)
        if removed == 0:
            return f"No entry contained '{substring}'."
        self._persist()
        self._snapshot_mtime = self._path.stat().st_mtime
        return f"Removed {removed} entr{'y' if removed == 1 else 'ies'}."

    def read(self) -> str:
        if not self._entries:
            return "(empty)"
        lines = [f"{i + 1}. {e}" for i, e in enumerate(self._entries)]
        return f"{self._total_chars()}/{self._max} chars\n" + "\n".join(lines)


class PersistentMemory:
    """Manages MEMORY.md and USER.md stores for a session.

    Instantiate once at session start via get_memory_manager().
    The frozen snapshot is safe to inject into the system prompt for the
    entire session lifetime.
    """

    def __init__(self, home: Path | None = None) -> None:
        base = home or _synapse_home()
        base.mkdir(parents=True, exist_ok=True)
        self.memory = _Store(base / "MEMORY.md", MEMORY_MAX_CHARS)
        self.user = _Store(base / "USER.md", USER_MAX_CHARS)

    def system_prompt_block(self) -> str:
        """Frozen memory blocks to inject into the system prompt."""
        blocks = []
        m = self.memory.prompt_block("AGENT MEMORY")
        u = self.user.prompt_block("USER PROFILE")
        if m:
            blocks.append(m)
        if u:
            blocks.append(u)
        return "\n\n".join(blocks)

    def dispatch(
        self,
        store: str,
        action: str,
        content: str = "",
        old_text: str = "",
    ) -> str:
        """Route a memory tool call to the correct store and action."""
        if store == "memory":
            s = self.memory
        elif store == "user":
            s = self.user
        else:
            return f"Error: unknown store '{store}'. Use 'memory' or 'user'."

        if action == "read":
            return s.read()
        if action == "add":
            return s.add(content)
        if action == "replace":
            if not old_text:
                return "Error: 'old_text' is required for replace."
            return s.replace(old_text, content)
        if action == "remove":
            return s.remove(content)
        return f"Error: unknown action '{action}'. Use add, replace, remove, or read."


_MANAGER: PersistentMemory | None = None


def get_memory_manager(home: Path | None = None) -> PersistentMemory:
    """Return the shared PersistentMemory instance, initialised once per process."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PersistentMemory(home)
    return _MANAGER
