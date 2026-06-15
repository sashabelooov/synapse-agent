"""transcribe_audio tool — speech-to-text.

Backends (set WHISPER_BACKEND in .env):
  openai  (default) — OpenAI Whisper API. Requires OPENAI_API_KEY.
                      Supports: ogg, mp3, wav, m4a, webm, mp4, flac.
  local             — faster-whisper running locally (requires Python 3.12+
                      and `uv pip install faster-whisper`). Falls back to
                      openai backend automatically if not importable.

Usage: transcribe_audio(path="recording.ogg")
       transcribe_audio(path="interview.mp3", language="en")
"""

from __future__ import annotations

import os
from pathlib import Path

from tools.base.tool import ToolDefinition

_SUPPORTED = {".ogg", ".mp3", ".wav", ".m4a", ".webm", ".mp4", ".flac", ".mpeg"}


def _backend() -> str:
    return os.environ.get("WHISPER_BACKEND", "openai").lower()


def _transcribe_openai(path: Path, language: str | None) -> str:
    """Transcribe via OpenAI Whisper API."""
    try:
        from openai import OpenAI
    except ImportError:
        return "Error: openai package not installed. Run: uv pip install openai"

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return "Error: OPENAI_API_KEY is not set in .env."

    client = OpenAI(api_key=api_key)
    with open(path, "rb") as f:
        kwargs: dict = {"model": "whisper-1", "file": f}
        if language:
            kwargs["language"] = language
        result = client.audio.transcriptions.create(**kwargs)
    return result.text.strip()


def _transcribe_local(path: Path, language: str | None) -> str:
    """Transcribe via faster-whisper (local CPU). Requires Python 3.12+."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return (
            "Error: faster-whisper is not installed or requires Python 3.12+. "
            "Set WHISPER_BACKEND=openai to use the OpenAI API instead."
        )

    model_size = os.environ.get("WHISPER_LOCAL_MODEL", "base")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), language=language or None)
    return " ".join(s.text.strip() for s in segments).strip()


def _transcribe(path: str, language: str = "") -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if p.suffix.lower() not in _SUPPORTED:
        return (
            f"Error: unsupported format '{p.suffix}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED))}"
        )

    lang = language.strip() or None
    backend = _backend()

    if backend == "local":
        result = _transcribe_local(p, lang)
        # Fall back to OpenAI API if local import failed
        if result.startswith("Error: faster-whisper"):
            result = _transcribe_openai(p, lang)
    else:
        result = _transcribe_openai(p, lang)

    return result or "(no speech detected)"


tool = ToolDefinition(
    name="transcribe_audio",
    description=(
        "Transcribe an audio file to text using Whisper. "
        "Supports ogg, mp3, wav, m4a, webm, mp4, flac. "
        "Use for voice messages, meeting recordings, or any audio input."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the audio file to transcribe.",
            },
            "language": {
                "type": "string",
                "description": (
                    "Optional ISO-639-1 language code (e.g. 'en', 'ru', 'es'). "
                    "Leave empty for auto-detection."
                ),
            },
        },
        "required": ["path"],
    },
    function=_transcribe,
)
