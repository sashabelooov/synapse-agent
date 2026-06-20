"""Tests for tools/generate_video/generate_video.py.

All API/library calls are mocked — no network needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen(**kwargs):
    from tools.generate_video.generate_video import _generate
    return _generate(**kwargs)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_prompt_and_no_image_returns_error(self):
        result = _gen(prompt="", image_path="")
        assert "prompt" in result.lower() or "error" in result.lower()

    def test_whitespace_prompt_and_no_image_returns_error(self):
        result = _gen(prompt="   ", image_path="")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# Replicate backend
# ---------------------------------------------------------------------------

class TestReplicateBackend:
    def test_missing_api_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        monkeypatch.setenv("VIDEO_BACKEND", "replicate")
        with patch.dict("sys.modules", {"replicate": MagicMock()}):
            result = _gen(prompt="a cat walks")
        assert "REPLICATE_API_TOKEN" in result

    def test_missing_replicate_package(self, monkeypatch):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        with patch.dict("sys.modules", {"replicate": None}):
            result = _gen(prompt="a cat walks", backend="replicate")
        assert "not installed" in result.lower()

    def test_successful_generation_url_string(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        video_url = "https://replicate.delivery/video.mp4"
        fake_replicate = MagicMock()
        fake_replicate.run.return_value = video_url

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            with patch("urllib.request.urlretrieve") as mock_dl:
                result = _gen(prompt="a cat walks", backend="replicate")

        fake_replicate.run.assert_called_once()
        call_args = fake_replicate.run.call_args
        assert call_args[1]["input"]["prompt"] == "a cat walks"
        mock_dl.assert_called_once()
        assert mock_dl.call_args[0][0] == video_url
        assert result.endswith(".mp4")

    def test_successful_generation_list_output(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        video_url = "https://replicate.delivery/video.mp4"
        fake_replicate = MagicMock()
        fake_replicate.run.return_value = [video_url]

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            with patch("urllib.request.urlretrieve") as mock_dl:
                result = _gen(prompt="a cat walks", backend="replicate")

        mock_dl.assert_called_once_with(video_url, mock_dl.call_args[0][1])

    def test_file_output_object(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        video_url = "https://replicate.delivery/video.mp4"
        fake_output = MagicMock()
        fake_output.url = video_url
        fake_replicate = MagicMock()
        fake_replicate.run.return_value = fake_output

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            with patch("urllib.request.urlretrieve") as mock_dl:
                _gen(prompt="a cat walks", backend="replicate")

        mock_dl.assert_called_once_with(video_url, mock_dl.call_args[0][1])

    def test_duration_forwarded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        fake_replicate = MagicMock()
        fake_replicate.run.return_value = "https://example.com/v.mp4"

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            with patch("urllib.request.urlretrieve"):
                _gen(prompt="a cat walks", duration=10, backend="replicate")

        input_params = fake_replicate.run.call_args[1]["input"]
        assert input_params["duration"] == 10

    def test_image_path_not_found_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        fake_replicate = MagicMock()
        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            result = _gen(
                prompt="a cat walks",
                image_path="/nonexistent/frame.png",
                backend="replicate",
            )
        assert "does not exist" in result

    def test_model_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        fake_replicate = MagicMock()
        fake_replicate.run.return_value = "https://example.com/v.mp4"

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            with patch("urllib.request.urlretrieve"):
                _gen(prompt="a cat walks", model="wan-ai/wan2.1-t2v-480p", backend="replicate")

        called_model = fake_replicate.run.call_args[0][0]
        assert called_model == "wan-ai/wan2.1-t2v-480p"

    def test_replicate_api_error_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        fake_replicate = MagicMock()
        fake_replicate.run.side_effect = RuntimeError("quota exceeded")

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            result = _gen(prompt="a cat walks", backend="replicate")

        assert "error" in result.lower()
        assert "quota exceeded" in result.lower()

    def test_default_backend_is_replicate(self, monkeypatch, tmp_path):
        monkeypatch.delenv("VIDEO_BACKEND", raising=False)
        monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        fake_replicate = MagicMock()
        fake_replicate.run.return_value = "https://example.com/v.mp4"

        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            with patch("urllib.request.urlretrieve"):
                result = _gen(prompt="a cat walks")

        # Reached replicate path (no token error)
        assert "REPLICATE_API_TOKEN" not in result
        assert "not installed" not in result.lower()


# ---------------------------------------------------------------------------
# RunwayML backend
# ---------------------------------------------------------------------------

class TestRunwayBackend:
    def test_missing_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
        monkeypatch.setenv("VIDEO_BACKEND", "runway")
        with patch.dict("sys.modules", {"runwayml": MagicMock()}):
            result = _gen(prompt="a cat walks", backend="runway")
        assert "RUNWAY_API_KEY" in result

    def test_missing_runwayml_package(self, monkeypatch):
        monkeypatch.setenv("RUNWAY_API_KEY", "key_test")
        with patch.dict("sys.modules", {"runwayml": None}):
            result = _gen(prompt="a cat walks", backend="runway")
        assert "not installed" in result.lower()

    def test_image_not_found_returns_error(self, monkeypatch):
        monkeypatch.setenv("RUNWAY_API_KEY", "key_test")
        fake_runwayml = MagicMock()
        with patch.dict("sys.modules", {"runwayml": fake_runwayml}):
            result = _gen(
                prompt="zoom in",
                image_path="/nonexistent/frame.png",
                backend="runway",
            )
        assert "does not exist" in result

    def test_successful_image_to_video(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RUNWAY_API_KEY", "key_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        # Create a dummy image file
        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

        video_url = "https://runway.ml/video.mp4"

        fake_task = MagicMock()
        fake_task.id = "task_abc"

        fake_status = MagicMock()
        fake_status.status = "SUCCEEDED"
        fake_status.output = [video_url]

        fake_client = MagicMock()
        fake_client.image_to_video.create.return_value = fake_task
        fake_client.tasks.retrieve.return_value = fake_status

        fake_runwayml = MagicMock()
        fake_runwayml.RunwayML.return_value = fake_client

        with patch.dict("sys.modules", {"runwayml": fake_runwayml}):
            with patch("urllib.request.urlretrieve") as mock_dl:
                with patch("base64.b64encode", return_value=b"ZmFrZQ=="):
                    result = _gen(
                        prompt="zoom in slowly",
                        image_path=str(img_path),
                        backend="runway",
                    )

        fake_client.image_to_video.create.assert_called_once()
        mock_dl.assert_called_once_with(video_url, mock_dl.call_args[0][1])
        assert result.endswith(".mp4")

    def test_task_failed_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RUNWAY_API_KEY", "key_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        img_path = tmp_path / "frame.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

        fake_task = MagicMock()
        fake_task.id = "task_fail"

        fake_status = MagicMock()
        fake_status.status = "FAILED"
        fake_status.failure = "content policy violation"

        fake_client = MagicMock()
        fake_client.image_to_video.create.return_value = fake_task
        fake_client.tasks.retrieve.return_value = fake_status

        fake_runwayml = MagicMock()
        fake_runwayml.RunwayML.return_value = fake_client

        with patch.dict("sys.modules", {"runwayml": fake_runwayml}):
            with patch("base64.b64encode", return_value=b"ZmFrZQ=="):
                result = _gen(
                    prompt="zoom in slowly",
                    image_path=str(img_path),
                    backend="runway",
                )

        assert "failed" in result.lower()

    def test_text_to_video_no_text_to_video_attr_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RUNWAY_API_KEY", "key_test")
        monkeypatch.setenv("VIDEO_OUTPUT_DIR", str(tmp_path))

        fake_client = MagicMock(spec=[
            "image_to_video", "tasks",
        ])  # no text_to_video attribute
        fake_runwayml = MagicMock()
        fake_runwayml.RunwayML.return_value = fake_client

        with patch.dict("sys.modules", {"runwayml": fake_runwayml}):
            result = _gen(prompt="a cat walks", backend="runway")

        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# Backend routing
# ---------------------------------------------------------------------------

class TestBackendRouting:
    def test_backend_override_routes_to_runway(self, monkeypatch):
        monkeypatch.setenv("VIDEO_BACKEND", "replicate")  # env says replicate
        monkeypatch.delenv("RUNWAY_API_KEY", raising=False)

        fake_runwayml = MagicMock()
        with patch.dict("sys.modules", {"runwayml": fake_runwayml}):
            result = _gen(prompt="a cat walks", backend="runway")

        assert "RUNWAY_API_KEY" in result  # hit runway path

    def test_backend_override_routes_to_replicate(self, monkeypatch):
        monkeypatch.setenv("VIDEO_BACKEND", "runway")  # env says runway
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)

        fake_replicate = MagicMock()
        with patch.dict("sys.modules", {"replicate": fake_replicate}):
            result = _gen(prompt="a cat walks", backend="replicate")

        assert "REPLICATE_API_TOKEN" in result  # hit replicate path


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_tool_is_registered(self):
        from tools.generate_video.generate_video import tool
        assert tool.name == "generate_video"

    def test_prompt_is_required(self):
        from tools.generate_video.generate_video import tool
        assert "prompt" in tool.parameters["required"]

    def test_tool_function_is_callable(self):
        from tools.generate_video.generate_video import tool
        assert callable(tool.function)

    def test_optional_params_present(self):
        from tools.generate_video.generate_video import tool
        props = tool.parameters["properties"]
        assert "duration" in props
        assert "image_path" in props
        assert "ratio" in props
        assert "backend" in props
        assert "model" in props
