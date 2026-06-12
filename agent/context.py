"""Smart context management.

A model's context window is a fixed budget shared between the conversation you
send IN and the reply it generates OUT. gpt-oss is 128K. The naive approach
(what v0.2 did) just deletes the oldest turns when full — which makes the agent
forget. This module is smarter, in three layers:

1. USE THE FULL WINDOW. Budget = window - output_reserve, so we never starve
   the reply but still use almost everything.

2. OFFLOAD BIG TOOL OUTPUTS TO RAG. The real space hogs aren't chat, they're
   tool results: one PDF read is ~16K tokens sitting in history forever. Once a
   large tool output is no longer recent, we store it in the vector store and
   replace it in history with a tiny pointer. A 16K dump becomes ~80 tokens, and
   nothing is lost — the agent can search_knowledge to get it back.

3. COMPACT OLD TURNS BY SUMMARY. If we're STILL over budget after offloading,
   we summarize the oldest turns into one short note instead of deleting them.
   Memory preserved, tokens reclaimed.

Token counts are estimated at ~4 chars/token. Approximate is fine: we only need
to stay comfortably under the real limit, and the output reserve is the cushion.
"""

import json
import hashlib

from config import get_context_window, get_output_reserve

# Keep this many most-recent messages verbatim, never offloaded or compacted.
# The model needs recent tool results and turns intact to keep working.
KEEP_RECENT = 6

# A tool output bigger than this (tokens) gets offloaded to RAG once it's old.
TOOL_OUTPUT_MAX_TOKENS = 1500

# Marker prefix so we never offload an already-offloaded message twice.
_OFFLOAD_MARK = "[offloaded:"

# Compact (summarize) once usage exceeds this fraction of the input budget.
COMPACT_TRIGGER = 0.80


def input_budget() -> int:
    """Tokens available for the conversation (window minus reply reserve)."""
    return max(get_context_window() - get_output_reserve(), 8000)


def estimate_tokens(messages: list[dict]) -> int:
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        else:
            total_chars += len(json.dumps(content, default=str))
        # tool_calls / extra structured fields add tokens too.
        if msg.get("tool_calls"):
            total_chars += len(json.dumps(msg["tool_calls"], default=str))
    return total_chars // 4


def _content_str(msg: dict) -> str:
    c = msg.get("content", "")
    return c if isinstance(c, str) else json.dumps(c, default=str)


# ---------------------------------------------------------------------------
# Layer 2: offload large, old tool outputs to RAG
# ---------------------------------------------------------------------------

def offload_tool_outputs(messages: list[dict]) -> list[dict]:
    """Replace big OLD tool results with a pointer; store full text in RAG."""
    cutoff = len(messages) - KEEP_RECENT  # don't touch recent messages
    if cutoff <= 0:
        return messages

    for i in range(cutoff):
        msg = messages[i]
        if msg.get("role") != "tool":
            continue
        content = _content_str(msg)
        if content.startswith(_OFFLOAD_MARK):
            continue  # already offloaded
        if len(content) // 4 <= TOOL_OUTPUT_MAX_TOKENS:
            continue  # small enough to keep

        digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:10]
        source = f"tool_output:{digest}"
        try:
            from agent import memory
            memory.add_text(content, source=source)
            recoverable = " Use search_knowledge to recall its details."
        except Exception:
            recoverable = ""  # RAG unavailable — still truncate to save space

        head = content[:200].replace("\n", " ")
        approx = len(content) // 4
        msg["content"] = (
            f"{_OFFLOAD_MARK}{source}] A large tool result (~{approx} tokens) was "
            f"moved out of the active context to save space. Preview: {head}...{recoverable}"
        )
    return messages


# ---------------------------------------------------------------------------
# Layer 3: compact old turns into a summary
# ---------------------------------------------------------------------------

def _render_for_summary(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "?")
        text = _content_str(m)
        if m.get("tool_calls"):
            text += " " + json.dumps(m["tool_calls"], default=str)
        lines.append(f"{role.upper()}: {text[:1500]}")
    return "\n".join(lines)


def _safe_recent_boundary(messages: list[dict], start: int) -> int:
    """Find a recent-window start that doesn't begin with an orphan tool result.

    A 'tool' message must follow the assistant message that called it. If our
    recent window would start on a tool message, walk back to include its owner.
    """
    idx = max(len(messages) - KEEP_RECENT, start)
    while idx > start and messages[idx].get("role") == "tool":
        idx -= 1
    return idx


def compact(messages: list[dict], adapter, model_name: str) -> list[dict]:
    """Summarize the oldest turns into one note, preserving recent turns."""
    system: list[dict] = []
    start = 0
    if messages and messages[0].get("role") == "system":
        system = [messages[0]]
        start = 1

    recent_start = _safe_recent_boundary(messages, start)
    old = messages[start:recent_start]
    recent = messages[recent_start:]
    if len(old) < 2:
        return messages  # nothing worth summarizing

    convo = _render_for_summary(old)
    try:
        resp = adapter.chat(
            model_name,
            [
                {"role": "system", "content": "You compress conversations. Summarize the exchange below into a dense bullet list capturing decisions, facts learned, files touched, and open threads. Be terse. No preamble."},
                {"role": "user", "content": convo[:40000]},
            ],
            [],  # no tools during summarization
        )
        summary_text, _, _ = adapter.parse_response(resp)
    except Exception:
        return messages  # summarization failed — leave as-is, hard trim will catch it

    if not summary_text.strip():
        return messages

    summary_msg = {
        "role": "system",
        "content": "[Summary of earlier conversation]\n" + summary_text.strip(),
    }
    return system + [summary_msg] + recent


# ---------------------------------------------------------------------------
# Hard fallback: drop oldest if still over budget
# ---------------------------------------------------------------------------

def hard_trim(messages: list[dict], max_tokens: int) -> list[dict]:
    if estimate_tokens(messages) <= max_tokens:
        return messages
    system: list[dict] = []
    rest = messages
    if messages and messages[0].get("role") == "system":
        system = [messages[0]]
        rest = messages[1:]
    while rest and estimate_tokens(system + rest) > max_tokens:
        rest = rest[1:]
        while rest and rest[0].get("role") == "tool":
            rest = rest[1:]
    return system + rest


# ---------------------------------------------------------------------------
# Entry point used by the loop
# ---------------------------------------------------------------------------

def manage_context(messages: list[dict], adapter=None, model_name: str | None = None) -> list[dict]:
    """Keep the conversation within budget while preserving as much as possible.

    Order: offload big tool outputs → compact old turns (if over trigger) →
    hard trim (last resort). adapter/model are needed only for compaction.
    """
    budget = input_budget()

    messages = offload_tool_outputs(messages)

    if (
        adapter is not None
        and model_name is not None
        and estimate_tokens(messages) > budget * COMPACT_TRIGGER
    ):
        messages = compact(messages, adapter, model_name)

    return hard_trim(messages, budget)


# Backwards-compatible alias (old name used elsewhere/tests).
def trim_history(messages: list[dict], max_tokens: int | None = None) -> list[dict]:
    return hard_trim(messages, max_tokens or input_budget())
