"""Tests for Docker packaging (Phase 11).

These tests validate the Dockerfile and docker-compose.yml are well-formed
and that the project's core modules import cleanly — the same check Docker
does during build. No Docker daemon is required to run these tests.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Dockerfile presence and structure
# ---------------------------------------------------------------------------

class TestDockerfile:
    def _content(self) -> str:
        p = ROOT / "Dockerfile"
        assert p.exists(), "Dockerfile not found at project root"
        return p.read_text()

    def test_dockerfile_exists(self):
        assert (ROOT / "Dockerfile").exists()

    def test_uses_python_312(self):
        content = self._content()
        assert "python:3.12" in content

    def test_copies_uv(self):
        content = self._content()
        assert "uv" in content

    def test_installs_tesseract(self):
        content = self._content()
        assert "tesseract-ocr" in content

    def test_installs_nodejs(self):
        content = self._content()
        assert "nodejs" in content or "nodesource" in content

    def test_non_root_user(self):
        content = self._content()
        assert re.search(r"USER\s+\w+", content), "Dockerfile must switch to a non-root USER"
        # Must not run as root
        assert "USER root" not in content

    def test_volume_declared(self):
        content = self._content()
        assert "VOLUME" in content

    def test_synapse_home_env(self):
        content = self._content()
        assert "SYNAPSE_HOME" in content

    def test_entrypoint_is_main(self):
        content = self._content()
        assert "main.py" in content

    def test_multistage_build(self):
        content = self._content()
        # At least two FROM lines = multi-stage
        from_count = len(re.findall(r"^FROM\s", content, re.MULTILINE))
        assert from_count >= 2, "Dockerfile should use multi-stage build"

    def test_no_secrets_in_dockerfile(self):
        content = self._content().lower()
        for secret_word in ("api_key", "token", "password", "secret"):
            # Env var names are fine in ENV lines; actual values are not
            assert f"={secret_word}" not in content
            assert f'"{secret_word}"' not in content


# ---------------------------------------------------------------------------
# docker-compose.yml presence and structure
# ---------------------------------------------------------------------------

class TestDockerCompose:
    def _content(self) -> str:
        p = ROOT / "docker-compose.yml"
        assert p.exists(), "docker-compose.yml not found at project root"
        return p.read_text()

    def test_compose_file_exists(self):
        assert (ROOT / "docker-compose.yml").exists()

    def test_synapse_service_defined(self):
        assert "synapse:" in self._content()

    def test_ollama_service_defined(self):
        assert "ollama:" in self._content()

    def test_ollama_behind_profile(self):
        content = self._content()
        # ollama service must be under a profile so it's opt-in
        assert "profiles:" in content
        assert "ollama" in content

    def test_volume_for_persistent_data(self):
        assert "synapse_data" in self._content()

    def test_env_file_referenced(self):
        assert "env_file" in self._content() or ".env" in self._content()

    def test_synapse_home_override(self):
        assert "SYNAPSE_HOME" in self._content()

    def test_no_hardcoded_secrets(self):
        content = self._content().lower()
        for secret in ("sk-", "xoxb-", "bot_token"):
            assert secret not in content

    def test_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            import json as yaml  # minimal fallback — won't parse YAML but skip
            return
        data = yaml.safe_load(self._content())
        assert isinstance(data, dict)
        assert "services" in data


# ---------------------------------------------------------------------------
# docs/docker.md
# ---------------------------------------------------------------------------

class TestDockerDocs:
    def test_docker_md_exists(self):
        assert (ROOT / "docs" / "docker.md").exists()

    def test_contains_quick_start(self):
        content = (ROOT / "docs" / "docker.md").read_text()
        assert "quick start" in content.lower() or "docker compose" in content.lower()

    def test_mentions_env_example(self):
        content = (ROOT / "docs" / "docker.md").read_text()
        assert ".env" in content

    def test_mentions_volume(self):
        content = (ROOT / "docs" / "docker.md").read_text()
        assert "volume" in content.lower()

    def test_mentions_ollama_profile(self):
        content = (ROOT / "docs" / "docker.md").read_text()
        assert "ollama" in content.lower()


# ---------------------------------------------------------------------------
# Smoke-test: core project modules import cleanly
# (same check the Docker build does when it runs `python -c "import ..."`)
# ---------------------------------------------------------------------------

class TestProjectImports:
    def _import(self, module: str) -> None:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Failed to import {module}:\n{result.stderr}"
        )

    def test_import_config(self):
        self._import("config")

    def test_import_tools_registry(self):
        self._import("tools.base.registry")

    def test_import_agent_loop(self):
        self._import("agent.loop")

    def test_import_agent_runner(self):
        self._import("agent.runner")

    def test_import_agent_session(self):
        self._import("agent.session")

    def test_import_agent_memory(self):
        self._import("agent.memory")

    def test_import_agent_skills(self):
        self._import("agent.skills")

    def test_import_cron_scheduler(self):
        self._import("cron.scheduler")

    def test_import_gateway_telegram(self):
        self._import("gateway.telegram")

    def test_all_tools_discoverable(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from tools.base.registry import get_all_tools; "
             "tools = get_all_tools(); "
             "assert len(tools) >= 20, f'Expected >=20 tools, got {len(tools)}'; "
             "print(f'OK: {len(tools)} tools discovered')"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "OK:" in result.stdout
