import os

import requests
from tools.base.tool import ToolDefinition


def _search_tavily(query: str, api_key: str) -> str:
    """Tavily returns clean ranked web results with snippets. Best option."""
    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": 5,
            "include_answer": True,
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    out = []
    if data.get("answer"):
        out.append(f"Answer: {data['answer']}\n")
    for r in data.get("results", []):
        out.append(f"- {r.get('title', '')}\n  {r.get('url', '')}\n  {r.get('content', '')[:300]}")
    return "\n".join(out) if out else "No results found."


def _search_ddg_html(query: str) -> str:
    """Keyless fallback: scrape DuckDuckGo's HTML endpoint for real results.

    Unlike the Instant Answers API (which only knows Wikipedia-ish topics),
    this returns actual ranked web results for technical queries.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "Error: beautifulsoup4 is required for keyless web search."

    response = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (compatible; AgentBot/1.0)"},
        timeout=15,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for result in soup.select(".result")[:5]:
        title_el = result.select_one(".result__a")
        snippet_el = result.select_one(".result__snippet")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        results.append(f"- {title}\n  {url}\n  {snippet}")

    return "\n".join(results) if results else "No results found."


def _web_search(query: str) -> str:
    """Search the web. Uses Tavily if TAVILY_API_KEY is set, else DuckDuckGo HTML."""
    try:
        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if tavily_key:
            return _search_tavily(query, tavily_key)
        return _search_ddg_html(query)
    except Exception as e:
        return f"Error searching: {e}"


tool = ToolDefinition(
    name="web_search",
    description="Search the internet for information. Use this when you need to find current information or documentation.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the internet.",
            },
        },
        "required": ["query"],
    },
    function=_web_search,
)
