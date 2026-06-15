"""text_to_speech tool — text-to-speech synthesis.

Backends (set TTS_BACKEND in .env):
  edge    (default) — Microsoft edge-tts (free, 300+ voices, requires internet).
                      Voice controlled by EDGE_TTS_VOICE (default: en-US-AriaNeural).
  openai            — OpenAI TTS API. Requires OPENAI_API_KEY.
                      Voice controlled by OPENAI_TTS_VOICE (default: alloy).
  pyttsx3           — Offline pyttsx3 (system TTS engine, no internet needed).

Output: saves mp3/wav to OUTPUT_DIR (default: /tmp) and returns the file path.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from tools.base.tool import ToolDefinition


def _backend() -> str:
    return os.environ.get("TTS_BACKEND", "edge").lower()


def _output_path(suffix: str) -> Path:
    output_dir = Path(os.environ.get("TTS_OUTPUT_DIR", tempfile.gettempdir()))
    output_dir.mkdir(parents=True, exist_ok=True)
    import time
    return output_dir / f"tts_{int(time.time() * 1000)}{suffix}"


def _tts_edge(text: str, voice: str | None) -> str:
    try:
        import edge_tts
    except ImportError:
        return "Error: edge-tts is not installed. Run: uv pip install edge-tts"

    selected_voice = voice or os.environ.get("EDGE_TTS_VOICE", "en-US-AriaNeural")
    out = _output_path(".mp3")
    communicate = edge_tts.Communicate(text, selected_voice)

    async def _run() -> None:
        await communicate.save(str(out))

    asyncio.run(_run())
    return str(out)


def _tts_openai(text: str, voice: str | None) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return "Error: openai package is not installed. Run: uv pip install openai"

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return "Error: OPENAI_API_KEY is not set in .env."

    selected_voice = voice or os.environ.get("OPENAI_TTS_VOICE", "alloy")
    out = _output_path(".mp3")
    client = OpenAI(api_key=api_key)
    response = client.audio.speech.create(
        model="tts-1",
        voice=selected_voice,
        input=text,
    )
    response.stream_to_file(str(out))
    return str(out)


def _tts_pyttsx3(text: str) -> str:
    try:
        import pyttsx3
    except ImportError:
        return "Error: pyttsx3 is not installed. Run: uv pip install pyttsx3"

    out = _output_path(".wav")
    engine = pyttsx3.init()
    engine.save_to_file(text, str(out))
    engine.runAndWait()
    return str(out)


def _speak(text: str, voice: str = "", backend: str = "") -> str:
    if not text.strip():
        return "Error: text is empty."

    selected = (backend.strip() or _backend()).lower()

    if selected == "openai":
        return _tts_openai(text, voice.strip() or None)
    elif selected == "pyttsx3":
        return _tts_pyttsx3(text)
    else:
        return _tts_edge(text, voice.strip() or None)


tool = ToolDefinition(
    name="text_to_speech",
    description=(
        "Convert text to speech and save as an audio file. "
        "Returns the path to the generated audio file (mp3 or wav). "
        "Useful for voice replies, reading documents aloud, or creating audio content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to convert to speech.",
            },
            "voice": {
                "type": "string",
                "description": (
                    "Optional voice name. For edge backend: e.g. 'en-US-AriaNeural', "
                    "'ru-RU-SvetlanaNeural'. For openai backend: 'alloy', 'echo', "
                    "'fable', 'onyx', 'nova', 'shimmer'. Leave empty to use default."
                ),
            },
            "backend": {
                "type": "string",
                "description": (
                    "Override TTS backend for this call: 'edge', 'openai', or 'pyttsx3'. "
                    "Leave empty to use TTS_BACKEND from .env (default: edge)."
                ),
            },
        },
        "required": ["text"],
    },
    function=_speak,
)
