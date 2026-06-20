"""Tests for tools/generate_image/generate_image.py.

All API/library calls are mocked — no network or GPU needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen(**kwargs):
    from tools.generate_image.generate_image import _generate
    return _generate(**kwargs)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_prompt_returns_error(self):
        result = _gen(prompt="")
        assert "empty" in result.lower()

    def test_whitespace_prompt_returns_error(self):
        result = _gen(prompt="   ")
        assert "empty" in result.lower()


# ---------------------------------------------------------------------------
# OpenAI / DALL-E backend
# ---------------------------------------------------------------------------

class TestOpenAIBackend:
    def test_missing_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("IMAGE_BACKEND", "openai")
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            result = _gen(prompt="a cat")
        assert "OPENAI_API_KEY" in result

    def test_invalid_size_returns_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_BACKEND", "openai")
        result = _gen(prompt="a cat", size="bad_size")
        assert "invalid size" in result.lower()

    def test_invalid_quality_returns_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_BACKEND", "openai")
        result = _gen(prompt="a cat", quality="ultra")
        assert "invalid quality" in result.lower()

    def test_successful_generation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_BACKEND", "openai")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))

        fake_url = "https://example.com/image.png"
        fake_response = MagicMock()
        fake_response.data = [MagicMock(url=fake_url)]

        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response

        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            with patch("urllib.request.urlretrieve") as mock_dl:
                result = _gen(prompt="a cat")

        fake_client.images.generate.assert_called_once()
        call_kwargs = fake_client.images.generate.call_args[1]
        assert call_kwargs["prompt"] == "a cat"
        assert call_kwargs["model"] == "dall-e-3"
        assert call_kwargs["size"] == "1024x1024"
        assert call_kwargs["quality"] == "standard"
        mock_dl.assert_called_once()
        assert mock_dl.call_args[0][0] == fake_url
        assert result.endswith(".png")

    def test_hd_quality_is_forwarded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))

        fake_response = MagicMock()
        fake_response.data = [MagicMock(url="https://example.com/x.png")]
        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response
        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            with patch("urllib.request.urlretrieve"):
                _gen(prompt="a cat", quality="hd", backend="openai")

        call_kwargs = fake_client.images.generate.call_args[1]
        assert call_kwargs["quality"] == "hd"

    def test_landscape_size_forwarded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))

        fake_response = MagicMock()
        fake_response.data = [MagicMock(url="https://example.com/x.png")]
        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response
        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            with patch("urllib.request.urlretrieve"):
                _gen(prompt="a landscape", size="1792x1024", backend="openai")

        call_kwargs = fake_client.images.generate.call_args[1]
        assert call_kwargs["size"] == "1792x1024"

    def test_model_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))

        fake_response = MagicMock()
        fake_response.data = [MagicMock(url="https://example.com/x.png")]
        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response
        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            with patch("urllib.request.urlretrieve"):
                _gen(prompt="a cat", model="dall-e-2", backend="openai")

        call_kwargs = fake_client.images.generate.call_args[1]
        assert call_kwargs["model"] == "dall-e-2"

    def test_no_url_in_response_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))

        fake_response = MagicMock()
        fake_response.data = [MagicMock(url=None)]
        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response
        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            result = _gen(prompt="a cat", backend="openai")

        assert "no image url" in result.lower()

    def test_missing_openai_package(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch.dict("sys.modules", {"openai": None}):
            result = _gen(prompt="a cat", backend="openai")
        assert "not installed" in result.lower()

    def test_backend_env_var_defaults_to_openai(self, monkeypatch, tmp_path):
        monkeypatch.delenv("IMAGE_BACKEND", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))

        fake_response = MagicMock()
        fake_response.data = [MagicMock(url="https://example.com/x.png")]
        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response
        fake_openai_module = MagicMock()
        fake_openai_module.OpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            with patch("urllib.request.urlretrieve"):
                result = _gen(prompt="a dog")

        # Should have reached openai backend (no "not installed" / "OPENAI_API_KEY" error)
        assert "OPENAI_API_KEY" not in result
        assert "not installed" not in result.lower()


# ---------------------------------------------------------------------------
# Diffusers backend
# ---------------------------------------------------------------------------

class TestDiffusersBackend:
    def test_missing_diffusers_package(self, monkeypatch):
        monkeypatch.setenv("IMAGE_BACKEND", "diffusers")
        with patch.dict("sys.modules", {"torch": None, "diffusers": None}):
            result = _gen(prompt="a cat", backend="diffusers")
        assert "not installed" in result.lower()

    def test_successful_generation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("IMAGE_BACKEND", "diffusers")
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("IMAGE_DEVICE", "cpu")

        fake_image = MagicMock()
        fake_pipeline_instance = MagicMock()
        fake_pipeline_instance.return_value.images = [fake_image]
        fake_pipeline_instance.to.return_value = fake_pipeline_instance

        fake_pipeline_class = MagicMock(return_value=fake_pipeline_instance)
        fake_pipeline_class.from_pretrained.return_value = fake_pipeline_instance

        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = False
        fake_torch.float32 = "float32"

        fake_diffusers = MagicMock()
        fake_diffusers.StableDiffusionPipeline = fake_pipeline_class

        with patch.dict("sys.modules", {"torch": fake_torch, "diffusers": fake_diffusers}):
            result = _gen(prompt="a cat", backend="diffusers")

        fake_image.save.assert_called_once()
        saved_path = fake_image.save.call_args[0][0]
        assert saved_path.endswith(".png")
        assert result == saved_path

    def test_model_load_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("IMAGE_DEVICE", "cpu")

        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = False
        fake_torch.float32 = "float32"

        fake_pipeline_class = MagicMock()
        fake_pipeline_class.from_pretrained.side_effect = RuntimeError("weights not found")
        fake_diffusers = MagicMock()
        fake_diffusers.StableDiffusionPipeline = fake_pipeline_class

        with patch.dict("sys.modules", {"torch": fake_torch, "diffusers": fake_diffusers}):
            result = _gen(prompt="a cat", backend="diffusers")

        assert "error loading" in result.lower()


# ---------------------------------------------------------------------------
# Backend routing via per-call override
# ---------------------------------------------------------------------------

class TestBackendOverride:
    def test_backend_override_routes_to_diffusers(self, monkeypatch):
        monkeypatch.setenv("IMAGE_BACKEND", "openai")  # env says openai

        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = False
        fake_torch.float32 = "float32"

        # Simulate diffusers missing so we can tell which path was taken
        with patch.dict("sys.modules", {"torch": None, "diffusers": None}):
            result = _gen(prompt="a cat", backend="diffusers")

        assert "not installed" in result.lower()  # hit diffusers path

    def test_backend_override_routes_to_openai(self, monkeypatch):
        monkeypatch.setenv("IMAGE_BACKEND", "diffusers")  # env says diffusers
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with patch.dict("sys.modules", {"openai": MagicMock()}):
            result = _gen(prompt="a cat", backend="openai")

        assert "OPENAI_API_KEY" in result  # hit openai path


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_tool_is_registered(self):
        from tools.generate_image.generate_image import tool
        assert tool.name == "generate_image"

    def test_prompt_is_required(self):
        from tools.generate_image.generate_image import tool
        assert "prompt" in tool.parameters["required"]

    def test_tool_function_is_callable(self):
        from tools.generate_image.generate_image import tool
        assert callable(tool.function)

    def test_optional_params_present(self):
        from tools.generate_image.generate_image import tool
        props = tool.parameters["properties"]
        assert "size" in props
        assert "quality" in props
        assert "backend" in props
        assert "model" in props
        assert "negative_prompt" in props
        assert "steps" in props
