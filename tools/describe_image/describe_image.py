from pathlib import Path

from tools.base.tool import ToolDefinition
from config import get_ollama_client, get_vision_model

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".gif", ".webp"}


def _describe_image(path: str, question: str = "Describe this image in detail.") -> str:
    """Send an image to a vision model and return what it sees.

    Unlike read_file's OCR (which only extracts text), this actually 'sees' the
    image — objects, colors, scenes, charts, people, layout. Runs on the cloud
    vision model, so it uses zero local capacity.
    """
    p = Path(path)
    if not p.exists():
        return f"Error: image not found: {path}"
    if p.suffix.lower() not in _IMAGE_EXTS:
        return f"Error: not an image file: {path} (expected one of {sorted(_IMAGE_EXTS)})"

    try:
        client = get_ollama_client()  # cloud host
        model = get_vision_model()
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": question, "images": [str(p)]}],
            stream=False,
        )
        return response.message.content or "(Vision model returned no description.)"
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            return (
                f"Error: vision model '{get_vision_model()}' is not available on your "
                f"Ollama host. Set VISION_MODEL to an available vision model. ({msg})"
            )
        return f"Error describing image: {msg}"


tool = ToolDefinition(
    name="describe_image",
    description=(
        "Look at an image and describe what it shows — objects, people, colors, "
        "scenes, charts, diagrams, layout. Use this for ANY question about what an "
        "image depicts (not just text). For reading text out of an image, read_file "
        "with OCR also works, but this understands visual content. Optionally pass a "
        "specific question about the image."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the image file.",
            },
            "question": {
                "type": "string",
                "description": "Optional specific question about the image (e.g. 'How many people are in this photo?'). Defaults to a general description.",
            },
        },
        "required": ["path"],
    },
    function=_describe_image,
)
