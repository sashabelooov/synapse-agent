"""generate_image tool — AI image generation.

Backends (set IMAGE_BACKEND in .env):
  openai    (default) — DALL-E 3 via OpenAI API. Requires OPENAI_API_KEY.
                        Sizes: 1024x1024 (default), 1792x1024, 1024x1792.
                        Quality: standard (default) or hd.
  diffusers           — Local Stable Diffusion via HuggingFace diffusers.
                        Model: IMAGE_DIFFUSERS_MODEL (default: runwayml/stable-diffusion-v1-5).
                        Device: IMAGE_DEVICE (default: cuda if available, else cpu).
                        Requires: uv add diffusers transformers accelerate torch

Output: saves PNG to IMAGE_OUTPUT_DIR (default: /tmp) and returns the file path.
"""

from __future__ import annotations

import os
import tempfile
import time
import urllib.request
from pathlib import Path

from tools.base.tool import ToolDefinition


def _backend() -> str:
    return os.environ.get("IMAGE_BACKEND", "openai").lower()


def _output_path(prefix: str = "image") -> Path:
    output_dir = Path(os.environ.get("IMAGE_OUTPUT_DIR", tempfile.gettempdir()))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{prefix}_{int(time.time() * 1000)}.png"


def _generate_openai(
    prompt: str,
    size: str,
    quality: str,
    model: str,
) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return "Error: openai package is not installed. Run: uv add openai"

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return "Error: OPENAI_API_KEY is not set in .env."

    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    if size not in valid_sizes:
        return f"Error: invalid size '{size}'. Valid sizes: {', '.join(sorted(valid_sizes))}."

    valid_quality = {"standard", "hd"}
    if quality not in valid_quality:
        return f"Error: invalid quality '{quality}'. Use 'standard' or 'hd'."

    client = OpenAI(api_key=api_key)
    response = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size=size,  # type: ignore[arg-type]
        quality=quality,  # type: ignore[arg-type]
        response_format="url",
    )

    image_url = response.data[0].url
    if not image_url:
        return "Error: OpenAI returned no image URL."

    out = _output_path("dalle")
    urllib.request.urlretrieve(image_url, str(out))
    return str(out)


def _generate_diffusers(prompt: str, negative_prompt: str, steps: int) -> str:
    try:
        import torch
        from diffusers import StableDiffusionPipeline
    except ImportError:
        return (
            "Error: diffusers/torch not installed. "
            "Run: uv add diffusers transformers accelerate torch"
        )

    model_id = os.environ.get(
        "IMAGE_DIFFUSERS_MODEL", "runwayml/stable-diffusion-v1-5"
    )
    device_pref = os.environ.get("IMAGE_DEVICE", "").strip()
    if device_pref:
        device = device_pref
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    dtype = torch.float16 if device == "cuda" else torch.float32

    try:
        pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe = pipe.to(device)
    except Exception as e:
        return f"Error loading diffusers model '{model_id}': {e}"

    try:
        result = pipe(
            prompt,
            negative_prompt=negative_prompt or None,
            num_inference_steps=steps,
        )
        image = result.images[0]
    except Exception as e:
        return f"Error generating image with diffusers: {e}"

    out = _output_path("sd")
    image.save(str(out))
    return str(out)


def _generate(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    negative_prompt: str = "",
    steps: int = 20,
    backend: str = "",
    model: str = "",
) -> str:
    if not prompt.strip():
        return "Error: prompt is empty."

    selected = (backend.strip() or _backend()).lower()

    if selected == "diffusers":
        return _generate_diffusers(prompt, negative_prompt, steps)
    else:
        # Default: openai / DALL-E
        selected_model = model.strip() or os.environ.get("IMAGE_MODEL", "dall-e-3")
        return _generate_openai(prompt, size, quality, selected_model)


tool = ToolDefinition(
    name="generate_image",
    description=(
        "Generate an image from a text prompt using AI. "
        "Default backend is DALL-E 3 (OpenAI). "
        "Can also use local Stable Diffusion (set IMAGE_BACKEND=diffusers). "
        "Returns the path to the saved PNG file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the image to generate. Be detailed and specific.",
            },
            "size": {
                "type": "string",
                "description": (
                    "Image dimensions (openai backend only). "
                    "Options: '1024x1024' (square, default), '1792x1024' (landscape), '1024x1792' (portrait)."
                ),
            },
            "quality": {
                "type": "string",
                "description": (
                    "Image quality (openai backend only). "
                    "'standard' (default, faster) or 'hd' (higher detail, slower)."
                ),
            },
            "negative_prompt": {
                "type": "string",
                "description": "Things to exclude from the image (diffusers backend only).",
            },
            "steps": {
                "type": "integer",
                "description": "Inference steps (diffusers backend only, default: 20). More steps = better quality but slower.",
            },
            "backend": {
                "type": "string",
                "description": (
                    "Override backend for this call: 'openai' (DALL-E 3) or 'diffusers' (local SD). "
                    "Leave empty to use IMAGE_BACKEND from .env (default: openai)."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Override model for openai backend: 'dall-e-3' (default) or 'dall-e-2'. "
                    "Leave empty to use IMAGE_MODEL from .env."
                ),
            },
        },
        "required": ["prompt"],
    },
    function=_generate,
)
