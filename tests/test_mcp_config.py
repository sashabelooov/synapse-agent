"""Tests for mcp_servers.json configuration (Phase 12).

Validates that all MCP server entries are well-formed and that
load_mcp_servers() handles env-expansion and missing credentials correctly.
No MCP daemons are started — this is pure config validation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP_FILE = ROOT / "mcp_servers.json"

EXPECTED_SERVERS = {
    "github",
    "playwright",
    "context7",
    "postgres",
    "filesystem",
    "slack",
}


# ---------------------------------------------------------------------------
# mcp_servers.json structure
# ---------------------------------------------------------------------------

class TestMcpServersJson:
    def _data(self) -> dict:
        assert MCP_FILE.exists(), "mcp_servers.json not found"
        return json.loads(MCP_FILE.read_text())

    def test_file_is_valid_json(self):
        json.loads(MCP_FILE.read_text())

    def test_all_expected_servers_present(self):
        data = self._data()
        for name in EXPECTED_SERVERS:
            assert name in data, f"Missing server entry: '{name}'"

    def test_each_entry_has_command(self):
        for name, spec in self._data().items():
            assert "command" in spec, f"Server '{name}' missing 'command'"
            assert isinstance(spec["command"], str) and spec["command"]

    def test_each_entry_has_args_list(self):
        for name, spec in self._data().items():
            if "args" in spec:
                assert isinstance(spec["args"], list), \
                    f"Server '{name}' args must be a list"

    def test_each_env_block_is_dict(self):
        for name, spec in self._data().items():
            if "env" in spec:
                assert isinstance(spec["env"], dict), \
                    f"Server '{name}' env must be a dict"

    def test_no_hardcoded_secrets(self):
        raw = MCP_FILE.read_text().lower()
        for bad in ("sk-", "xoxb-", "ghp_", "postgresql://user:pass"):
            assert bad not in raw, f"Possible hardcoded secret ({bad!r}) in mcp_servers.json"

    def test_secrets_are_env_refs(self):
        """All credential-like values must use ${VAR} substitution."""
        data = self._data()
        for name, spec in data.items():
            for key, val in (spec.get("env") or {}).items():
                if any(k in key.upper() for k in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
                    assert "${" in str(val), (
                        f"Server '{name}' env var '{key}' must use ${{VAR}} substitution, "
                        f"got: {val!r}"
                    )

    # Individual server checks
    def test_github_uses_docker(self):
        assert self._data()["github"]["command"] == "docker"

    def test_playwright_uses_npx(self):
        assert self._data()["playwright"]["command"] == "npx"

    def test_context7_uses_npx(self):
        spec = self._data()["context7"]
        assert spec["command"] == "npx"
        assert any("context7" in str(a) for a in spec["args"])

    def test_postgres_uses_uvx(self):
        spec = self._data()["postgres"]
        assert spec["command"] == "uvx"
        assert any("postgres" in str(a) for a in spec["args"])

    def test_filesystem_uses_npx(self):
        spec = self._data()["filesystem"]
        assert spec["command"] == "npx"
        assert any("filesystem" in str(a) for a in spec["args"])

    def test_slack_uses_npx(self):
        spec = self._data()["slack"]
        assert spec["command"] == "npx"
        assert any("slack" in str(a) for a in spec["args"])

    def test_slack_requires_bot_token_env(self):
        spec = self._data()["slack"]
        env_vals = " ".join(str(v) for v in (spec.get("env") or {}).values())
        assert "SLACK_BOT_TOKEN" in env_vals

    def test_postgres_requires_connection_string_env(self):
        spec = self._data()["postgres"]
        combined = " ".join(spec.get("args", [])) + " ".join(
            str(v) for v in (spec.get("env") or {}).values()
        )
        assert "POSTGRES_CONNECTION_STRING" in combined


# ---------------------------------------------------------------------------
# load_mcp_servers() behaviour
# ---------------------------------------------------------------------------

class TestLoadMcpServers:
    def test_returns_dict(self):
        from config import load_mcp_servers
        result = load_mcp_servers()
        assert isinstance(result, dict)

    def test_all_servers_loaded(self):
        from config import load_mcp_servers
        result = load_mcp_servers()
        for name in EXPECTED_SERVERS:
            assert name in result, f"load_mcp_servers() missing '{name}'"

    def test_each_loaded_entry_has_command(self):
        from config import load_mcp_servers
        for name, spec in load_mcp_servers().items():
            assert "command" in spec
            assert isinstance(spec["command"], str)

    def test_env_vars_expanded(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_TEAM_ID", "T12345")
        from config import load_mcp_servers
        import importlib, config
        importlib.reload(config)
        result = config.load_mcp_servers()
        slack_env = result["slack"]["env"]
        assert slack_env.get("SLACK_BOT_TOKEN") == "xoxb-test-token"
        assert slack_env.get("SLACK_TEAM_ID") == "T12345"

    def test_missing_env_vars_expand_to_empty(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_CONNECTION_STRING", raising=False)
        from config import load_mcp_servers
        result = load_mcp_servers()
        pg_env = result["postgres"]["env"]
        assert pg_env.get("POSTGRES_CONNECTION_STRING") == ""

    def test_context7_needs_no_credentials(self):
        """Context7 should work without any env vars."""
        from config import load_mcp_servers
        result = load_mcp_servers()
        c7 = result["context7"]
        # env block may be empty or absent — that's correct
        assert c7.get("env", {}) == {} or all(
            v == "" for v in c7["env"].values()
        )

    def test_github_read_only_flag(self):
        from config import load_mcp_servers
        result = load_mcp_servers()
        assert result["github"]["env"].get("GITHUB_READ_ONLY") == "1"

    def test_github_toolsets(self):
        from config import load_mcp_servers
        result = load_mcp_servers()
        toolsets = result["github"]["env"].get("GITHUB_TOOLSETS", "")
        assert "repos" in toolsets
        assert "issues" in toolsets


# ---------------------------------------------------------------------------
# .env.example completeness
# ---------------------------------------------------------------------------

class TestEnvExample:
    def _content(self) -> str:
        p = ROOT / ".env.example"
        assert p.exists(), ".env.example not found"
        return p.read_text()

    def test_postgres_connection_string_documented(self):
        assert "POSTGRES_CONNECTION_STRING" in self._content()

    def test_filesystem_allowed_dirs_documented(self):
        assert "FILESYSTEM_ALLOWED_DIRS" in self._content()

    def test_slack_bot_token_documented(self):
        assert "SLACK_BOT_TOKEN" in self._content()

    def test_slack_team_id_documented(self):
        assert "SLACK_TEAM_ID" in self._content()

    def test_no_real_secrets_in_example(self):
        content = self._content()
        for bad in ("sk-", "xoxb-", "ghp_", "postgresql://user:real"):
            assert bad not in content
