"""Integration test: connect to the GitHub MCP server and list its tools.

Run directly:   uv run python3 test_mcp_github.py
Or with pytest: uv run pytest test_mcp_github.py -v

Requires Docker running and GITHUB_PERSONAL_ACCESS_TOKEN set in .env. If those
aren't available the test skips (pytest) or reports clearly (direct run) rather
than failing hard, since it depends on external services.
"""

from __future__ import annotations

import shutil

from dotenv import load_dotenv

load_dotenv()

from config import load_mcp_servers
from agent.mcp_client import MCPManager, MCPServerError


def _prereqs_ok() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "docker not found on PATH"
    servers = load_mcp_servers()
    if "github" not in servers:
        return False, "no 'github' server in mcp_servers.json"
    if not servers["github"]["env"].get("GITHUB_PERSONAL_ACCESS_TOKEN"):
        return False, "GITHUB_PERSONAL_ACCESS_TOKEN not set in .env"
    return True, ""


def test_github_mcp_lists_tools() -> None:
    ok, reason = _prereqs_ok()
    if not ok:
        try:
            import pytest

            pytest.skip(reason)
        except ImportError:
            print(f"SKIP: {reason}")
            return

    servers = load_mcp_servers()
    spec = servers["github"]
    manager = MCPManager()
    try:
        manager.connect("github", spec["command"], spec["args"], spec["env"])
        existing: set[str] = set()
        tools = manager.build_tool_definitions("github", existing)

        assert tools, "GitHub MCP server returned no tools"
        names = [t.name for t in tools]
        # Sanity: read-only repo/issue/PR toolsets should expose familiar tools.
        assert any("issue" in n or "pull" in n or "repo" in n for n in names), (
            f"expected repo/issue/PR tools, got: {names[:10]}"
        )

        print(f"\nConnected. {len(tools)} GitHub MCP tools available.")
        print("Sample:", ", ".join(names[:12]))
    finally:
        manager.shutdown()


if __name__ == "__main__":
    test_github_mcp_lists_tools()
    print("OK")
