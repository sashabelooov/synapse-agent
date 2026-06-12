"""Structured thinking — the real version.

Two ways a model can show its reasoning:

1. NATIVE thinking. Reasoning models (gpt-oss via Ollama, Claude extended
   thinking) return their reasoning in a dedicated channel, separate from the
   answer. The adapter pulls it out and hands it to the loop. This is the good
   path — real reasoning tokens, not a prompt trick.

2. PROMPTED scratchpad (fallback). Models with no native reasoning channel
   (e.g. gpt-4o) are asked to wrap their reasoning in <thinking>...</thinking>
   tags. We then split that out of the answer ourselves.

Either way, the reasoning ends up in its own channel and is rendered separately
from the user-facing answer — never grepped out of mixed text the way v0.2 did.
"""

import re

from termcolor import colored

# Appended to the system prompt ONLY for models without native thinking.
FALLBACK_INSTRUCTION = (
    "\n\nBefore answering or calling a tool, reason step by step inside "
    "<thinking>...</thinking> tags. Put ONLY your private reasoning there. "
    "After the closing tag, give your actual answer or call the tool. "
    "Keep the thinking concise."
)

_THINK_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL | re.IGNORECASE)


def split_thinking(content: str) -> tuple[str | None, str]:
    """Split <thinking> blocks out of text content.

    Returns (thinking, clean_content). Used for fallback (prompted) models.
    If there are no tags, thinking is None and content is returned unchanged.
    """
    if not content or "<thinking>" not in content.lower():
        return None, content

    blocks = _THINK_RE.findall(content)
    thinking = "\n".join(b.strip() for b in blocks).strip() or None
    clean = _THINK_RE.sub("", content).strip()
    return thinking, clean


def render_thinking(thinking: str | None) -> None:
    """Render reasoning in its own dim channel, visually distinct from answers."""
    if not thinking:
        return
    print(colored("💭 thinking", "blue", attrs=["bold"]))
    for line in thinking.strip().splitlines():
        if line.strip():
            print(colored("   " + line, "blue", attrs=["dark"]))
