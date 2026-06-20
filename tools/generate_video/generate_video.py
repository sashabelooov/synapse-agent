"""generate_video tool — AI video generation.

Backends (set VIDEO_BACKEND in .env):
  replicate (default) — Replicate cloud API. Requires REPLICATE_API_TOKEN.
                        Model: VIDEO_REPLICATE_MODEL
                        (default: minimax/video-01-live for text-to-video).
  runway              — RunwayML API. Requires RUNWAY_API_KEY.
                        Model: gen3a_turbo (text-to-video) or
                               gen3a_turbo image-to-video when image_path is provided.

Output: saves MP4 to VIDEO_OUTPUT_DIR (default: /tmp) and returns the file path.
"""

from __future__ import annotations

import os
import tempfile
import time
import urllib.request
from pathlib import Path

from tools.base.tool import ToolDefinition

_DEFAULT_REPLICATE_MODEL = "minimax/video-01-live"
_POLL_INTERVAL = 5   # seconds between status checks
_MAX_WAIT = 600      # 10 minutes hard timeout


def _backend() -> str:
    return os.environ.get("VIDEO_BACKEND", "replicate").lower()


def _output_path(prefix: str = "video") -> Path:
    output_dir = Path(os.environ.get("VIDEO_OUTPUT_DIR", tempfile.gettempdir()))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{prefix}_{int(time.time() * 1000)}.mp4"


def _download(url: str, dest: Path) -> str:
    try:
        urllib.request.urlretrieve(url, str(dest))
        return str(dest)
    except Exception as e:
        return f"Error downloading video from {url}: {e}"


def _generate_replicate(
    prompt: str,
    duration: int,
    image_path: str,
    model: str,
) -> str:
    try:
        import replicate
    except ImportError:
        return "Error: replicate package is not installed. Run: uv add replicate"

    api_token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not api_token:
        return "Error: REPLICATE_API_TOKEN is not set in .env."

    os.environ["REPLICATE_API_TOKEN"] = api_token

    selected_model = model.strip() or os.environ.get(
        "VIDEO_REPLICATE_MODEL", _DEFAULT_REPLICATE_MODEL
    )

    input_params: dict = {"prompt": prompt}
    if duration:
        input_params["duration"] = duration
    if image_path.strip():
        p = Path(image_path.strip())
        if not p.exists():
            return f"Error: image_path '{image_path}' does not exist."
        with open(p, "rb") as f:
            input_params["first_frame_image"] = f

    try:
        output = replicate.run(selected_model, input=input_params)
    except Exception as e:
        return f"Error calling Replicate API: {e}"

    # Output can be a URL string, a list, or a FileOutput object
    if isinstance(output, list):
        url = str(output[0])
    elif hasattr(output, "url"):
        url = output.url
    else:
        url = str(output)

    out = _output_path("replicate")
    return _download(url, out)


def _generate_runway(
    prompt: str,
    duration: int,
    image_path: str,
    ratio: str,
) -> str:
    try:
        import runwayml
    except ImportError:
        return "Error: runwayml package is not installed. Run: uv add runwayml"

    api_key = os.environ.get("RUNWAY_API_KEY", "").strip()
    if not api_key:
        return "Error: RUNWAY_API_KEY is not set in .env."

    client = runwayml.RunwayML(api_key=api_key)

    try:
        if image_path.strip():
            # Image-to-video
            p = Path(image_path.strip())
            if not p.exists():
                return f"Error: image_path '{image_path}' does not exist."
            import base64
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            suffix = p.suffix.lstrip(".").lower() or "png"
            mime = f"image/{suffix}"
            data_uri = f"data:{mime};base64,{b64}"

            task = client.image_to_video.create(
                model="gen4_turbo",
                prompt_image=data_uri,
                prompt_text=prompt or None,
                duration=duration or 5,
                ratio=ratio or "1280:720",
            )
        else:
            # Text-to-video — Gen-4 Turbo does not have a dedicated text-to-video
            # endpoint, so we use text_to_video if available, else image_to_video
            # with a blank frame. Fall back gracefully.
            try:
                task = client.text_to_video.create(  # type: ignore[attr-defined]
                    model="gen4_turbo",
                    prompt_text=prompt,
                    duration=duration or 5,
                    ratio=ratio or "1280:720",
                )
            except AttributeError:
                return (
                    "Error: RunwayML text-to-video requires an image input with gen4_turbo. "
                    "Provide an image_path or switch to VIDEO_BACKEND=replicate."
                )
    except Exception as e:
        return f"Error creating RunwayML task: {e}"

    # Poll until done
    task_id = task.id
    deadline = time.time() + _MAX_WAIT
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL)
        try:
            status = client.tasks.retrieve(task_id)
        except Exception as e:
            return f"Error polling RunwayML task {task_id}: {e}"

        if status.status == "SUCCEEDED":
            video_url = status.output[0] if status.output else None
            if not video_url:
                return "Error: RunwayML task succeeded but returned no output URL."
            out = _output_path("runway")
            return _download(video_url, out)

        if status.status in ("FAILED", "CANCELLED"):
            reason = getattr(status, "failure", status.status)
            return f"Error: RunwayML task {status.status}: {reason}"

    return f"Error: RunwayML task {task_id} did not complete within {_MAX_WAIT}s."


def _generate(
    prompt: str,
    duration: int = 5,
    image_path: str = "",
    ratio: str = "1280:720",
    backend: str = "",
    model: str = "",
) -> str:
    if not prompt.strip() and not image_path.strip():
        return "Error: provide a prompt, an image_path, or both."

    selected = (backend.strip() or _backend()).lower()

    if selected == "runway":
        return _generate_runway(prompt, duration, image_path, ratio)
    else:
        return _generate_replicate(prompt, duration, image_path, model)


tool = ToolDefinition(
    name="generate_video",
    description=(
        "Generate a short video from a text prompt (and optionally a starting image) using AI. "
        "Default backend is Replicate. RunwayML is also supported. "
        "Returns the path to the saved MP4 file. "
        "Note: video generation takes 30–120 seconds depending on the backend."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the video to generate. Describe motion, scene, style.",
            },
            "duration": {
                "type": "integer",
                "description": "Video length in seconds (default: 5). Supported range depends on the model.",
            },
            "image_path": {
                "type": "string",
                "description": (
                    "Optional path to a local image file to use as the first frame "
                    "(image-to-video mode). Leave empty for text-to-video."
                ),
            },
            "ratio": {
                "type": "string",
                "description": (
                    "Aspect ratio (runway backend only). "
                    "Examples: '1280:720' (landscape, default), '720:1280' (portrait), '1:1' (square)."
                ),
            },
            "backend": {
                "type": "string",
                "description": (
                    "Override backend: 'replicate' (default) or 'runway'. "
                    "Leave empty to use VIDEO_BACKEND from .env."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Override Replicate model ID (replicate backend only). "
                    "Leave empty to use VIDEO_REPLICATE_MODEL from .env "
                    f"(default: {_DEFAULT_REPLICATE_MODEL})."
                ),
            },
        },
        "required": ["prompt"],
    },
    function=_generate,
)
