import requests
from tools.base.tool import ToolDefinition


def _read_url(url: str) -> str:
    """Fetch a web page and return its text content."""
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AgentBot/1.0)",
            },
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        # If it's plain text or JSON, return directly
        if "text/plain" in content_type or "application/json" in content_type:
            return response.text[:10000]

        # For HTML, try to extract clean text
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Collapse multiple blank lines
            lines = [line for line in text.splitlines() if line.strip()]
            return "\n".join(lines)[:10000]
        except ImportError:
            # Fallback without BeautifulSoup — basic tag stripping
            import re

            text = re.sub(r"<[^>]+>", "", response.text)
            return text[:10000]

    except Exception as e:
        return f"Error fetching URL: {e}"


tool = ToolDefinition(
    name="read_url",
    description="Fetch a web page URL and return its text content. Use this to read documentation, APIs, or any web page.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch and read.",
            },
        },
        "required": ["url"],
    },
    function=_read_url,
)
