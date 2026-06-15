"""Tests for voice pipeline — transcribe_audio and text_to_speech tools."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.transcribe.transcribe import _transcribe, _transcribe_openai, _transcribe_local
from tools.tts.tts import _speak, _tts_edge, _tts_openai, _tts_pyttsx3, tool as tts_tool
from tools.transcribe.transcribe import tool as transcribe_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dummy_audio(suffix: str = ".ogg") -> str:
    """Create a non-empty temp file that looks like an audio file."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(b"\x00" * 128)
        return f.name


# ---------------------------------------------------------------------------
# transcribe_audio — file validation
# ---------------------------------------------------------------------------

class TestTranscribeValidation:
    def test_missing_file_returns_error(self):
        result = _transcribe("/nonexistent/path/audio.ogg")
        assert result.startswith("Error:") and "not found" in result

    def test_unsupported_format_returns_error(self, tmp_path):
        f = tmp_path / "audio.xyz"
        f.write_bytes(b"\x00")
        result = _transcribe(str(f))
        assert result.startswith("Error:") and "unsupported" in result.lower()

    def test_supported_formats_pass_validation(self):
        for ext in [".ogg", ".mp3", ".wav", ".m4a", ".webm", ".mp4", ".flac"]:
            path = _make_dummy_audio(ext)
            try:
                # Reaches backend, not validation error
                with patch("tools.transcribe.transcribe._transcribe_openai", return_value="ok"):
                    result = _transcribe(path)
                assert result == "ok"
            finally:
                Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# transcribe_audio — OpenAI backend
# ---------------------------------------------------------------------------

class TestTranscribeOpenAI:
    def test_missing_api_key_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        f = tmp_path / "audio.ogg"
        f.write_bytes(b"\x00")
        result = _transcribe_openai(f, None)
        assert result.startswith("Error:") and "OPENAI_API_KEY" in result

    def test_calls_whisper_api(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        f = tmp_path / "audio.ogg"
        f.write_bytes(b"\x00")

        mock_result = MagicMock()
        mock_result.text = "  Hello world  "
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        with patch("openai.OpenAI", return_value=mock_client):
            result = _transcribe_openai(f, None)

        assert result == "Hello world"
        mock_client.audio.transcriptions.create.assert_called_once()

    def test_language_passed_to_api(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        f = tmp_path / "audio.ogg"
        f.write_bytes(b"\x00")

        mock_result = MagicMock()
        mock_result.text = "Привет"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        with patch("openai.OpenAI", return_value=mock_client):
            _transcribe_openai(f, "ru")

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs.get("language") == "ru"

    def test_no_language_omits_language_param(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        f = tmp_path / "audio.ogg"
        f.write_bytes(b"\x00")

        mock_result = MagicMock()
        mock_result.text = "Hello"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        with patch("openai.OpenAI", return_value=mock_client):
            _transcribe_openai(f, None)

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert "language" not in call_kwargs


# ---------------------------------------------------------------------------
# transcribe_audio — local backend fallback
# ---------------------------------------------------------------------------

class TestTranscribeLocal:
    def test_falls_back_to_openai_if_faster_whisper_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("WHISPER_BACKEND", "local")
        f = tmp_path / "audio.ogg"
        f.write_bytes(b"\x00")

        with patch("builtins.__import__", side_effect=ImportError("no module")):
            result = _transcribe_local(f, None)
        assert result.startswith("Error: faster-whisper")

    def test_local_backend_env_triggers_local_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WHISPER_BACKEND", "local")
        f = tmp_path / "audio.ogg"
        f.write_bytes(b"\x00")

        with patch("tools.transcribe.transcribe._transcribe_local", return_value="local transcript") as mock_local:
            with patch("tools.transcribe.transcribe._transcribe_openai", return_value="openai transcript") as mock_oai:
                result = _transcribe(str(f))

        mock_local.assert_called_once()
        assert result == "local transcript"


# ---------------------------------------------------------------------------
# transcribe_audio — tool definition
# ---------------------------------------------------------------------------

class TestTranscribeTool:
    def test_tool_name(self):
        assert transcribe_tool.name == "transcribe_audio"

    def test_required_params(self):
        assert "path" in transcribe_tool.parameters["required"]

    def test_optional_language_param(self):
        assert "language" in transcribe_tool.parameters["properties"]


# ---------------------------------------------------------------------------
# text_to_speech — edge backend
# ---------------------------------------------------------------------------

class TestTTSEdge:
    def test_missing_edge_tts_returns_error(self, monkeypatch):
        with patch.dict("sys.modules", {"edge_tts": None}):
            result = _tts_edge("Hello", None)
        assert result.startswith("Error:") and "edge-tts" in result

    def test_calls_communicate_and_saves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))

        mock_communicate = MagicMock()
        mock_communicate.save = MagicMock(return_value=None)
        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_communicate

        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            with patch("asyncio.run"):
                result = _tts_edge("Hello world", "en-US-AriaNeural")

        assert result.endswith(".mp3")

    def test_default_voice_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("EDGE_TTS_VOICE", "ru-RU-SvetlanaNeural")

        mock_communicate = MagicMock()
        mock_communicate.save = MagicMock(return_value=None)
        mock_edge = MagicMock()
        mock_edge.Communicate.return_value = mock_communicate

        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            with patch("asyncio.run"):
                _tts_edge("Привет", None)

        # Communicate is called before asyncio.run, so the mock captures the call
        mock_edge.Communicate.assert_called_once_with("Привет", "ru-RU-SvetlanaNeural")


# ---------------------------------------------------------------------------
# text_to_speech — OpenAI backend
# ---------------------------------------------------------------------------

class TestTTSOpenAI:
    def test_missing_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = _tts_openai("Hello", None)
        assert result.startswith("Error:") and "OPENAI_API_KEY" in result

    def test_calls_openai_speech(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))

        mock_response = MagicMock()
        mock_client = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            result = _tts_openai("Hello", "nova")

        assert result.endswith(".mp3")
        mock_response.stream_to_file.assert_called_once()

    def test_voice_param_passed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))

        mock_response = MagicMock()
        mock_client = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            _tts_openai("Hi", "fable")

        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["voice"] == "fable"


# ---------------------------------------------------------------------------
# text_to_speech — pyttsx3 backend
# ---------------------------------------------------------------------------

class TestTTSPyttsx3:
    def test_missing_pyttsx3_returns_error(self):
        with patch.dict("sys.modules", {"pyttsx3": None}):
            result = _tts_pyttsx3("Hello")
        assert result.startswith("Error:") and "pyttsx3" in result

    def test_calls_engine(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))
        mock_engine = MagicMock()
        mock_pyttsx3 = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine

        with patch.dict("sys.modules", {"pyttsx3": mock_pyttsx3}):
            result = _tts_pyttsx3("Hello world")

        assert result.endswith(".wav")
        mock_engine.save_to_file.assert_called_once()
        mock_engine.runAndWait.assert_called_once()


# ---------------------------------------------------------------------------
# text_to_speech — _speak dispatcher
# ---------------------------------------------------------------------------

class TestTTSSpeak:
    def test_empty_text_returns_error(self):
        result = _speak("   ")
        assert result.startswith("Error:") and "empty" in result

    def test_backend_override_routes_to_openai(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))

        mock_response = MagicMock()
        mock_client = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            _speak("Hello", backend="openai")

        mock_client.audio.speech.create.assert_called_once()

    def test_backend_override_routes_to_pyttsx3(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))
        mock_engine = MagicMock()
        mock_pyttsx3 = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine

        with patch.dict("sys.modules", {"pyttsx3": mock_pyttsx3}):
            result = _speak("Hello", backend="pyttsx3")

        assert result.endswith(".wav")

    def test_default_backend_is_edge(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TTS_OUTPUT_DIR", str(tmp_path))
        monkeypatch.delenv("TTS_BACKEND", raising=False)

        with patch("tools.tts.tts._tts_edge", return_value="/tmp/out.mp3") as mock_edge:
            result = _speak("Hello")

        mock_edge.assert_called_once()


# ---------------------------------------------------------------------------
# text_to_speech — tool definition
# ---------------------------------------------------------------------------

class TestTTSTool:
    def test_tool_name(self):
        assert tts_tool.name == "text_to_speech"

    def test_required_params(self):
        assert "text" in tts_tool.parameters["required"]

    def test_optional_voice_param(self):
        assert "voice" in tts_tool.parameters["properties"]

    def test_optional_backend_param(self):
        assert "backend" in tts_tool.parameters["properties"]
