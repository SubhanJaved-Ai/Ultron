"""Tests for ClawHub community skill tools & on-demand subagent auto-loading."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from openjarvis.agents.subagents import (
    reset_subagent_manager,
)
from openjarvis.core.registry import ToolRegistry
from openjarvis.skills.sources.openclaw import OpenClawResolver
from openjarvis.tools.clawhub_tools import (
    ClawHubInfoTool,
    ClawHubInstallTool,
    ClawHubListInstalledTool,
    ClawHubSearchTool,
    _resolve_all_clawhub_skills,
)


class TestClawHubTools:
    def test_clawhub_search_curated(self):
        tool = ClawHubSearchTool()

        # Search for scraper
        res = tool.execute(query="scraper")
        assert res.success is True
        data = json.loads(res.content)
        assert data["total_matches"] >= 1
        names = [s["name"] for s in data["skills"]]
        assert "web-scraper" in names

        # Search by category
        res_cat = tool.execute(category="design")
        assert res_cat.success is True
        cat_data = json.loads(res_cat.content)
        cat_names = [s["name"] for s in cat_data["skills"]]
        assert "figma-tokens" in cat_names

    def test_clawhub_info(self):
        tool = ClawHubInfoTool()

        # Existing skill
        res = tool.execute(skill_name="docker-compose")
        assert res.success is True
        data = json.loads(res.content)
        assert data["name"] == "docker-compose"
        assert data["category"] == "devops"
        assert "multi-service" in data["description"].lower()

        # Non-existent skill
        res_missing = tool.execute(skill_name="completely_unknown_skill_xyz")
        assert res_missing.success is False
        assert "not found" in res_missing.content.lower()

    def test_clawhub_install_and_tool_registration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Redirect config dir to tmp_path for test isolation
        monkeypatch.setattr(
            "openjarvis.tools.clawhub_tools.get_config_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "openjarvis.skills.importer.get_config_dir", lambda: tmp_path
        )

        install_tool = ClawHubInstallTool()
        res = install_tool.execute(skill_name="figma-tokens", force=True)

        assert res.success is True
        data = json.loads(res.content)
        assert data["skill_name"] == "figma-tokens"
        assert data["status"] == "installed"

        # Verify tool was compiled into ToolRegistry
        assert ToolRegistry.contains("figma-tokens")
        compiled_tool = ToolRegistry.create("figma-tokens")
        assert compiled_tool is not None
        assert compiled_tool.spec.name in ("figma-tokens", "skill_figma-tokens")

    def test_clawhub_install_from_openclaw_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            "openjarvis.tools.clawhub_tools.get_config_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "openjarvis.skills.importer.get_config_dir", lambda: tmp_path
        )

        # Setup mock cache
        cache_dir = tmp_path / "cache"
        skill_dir = cache_dir / "skills" / "alice" / "etherscan-data"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
                ---
                name: etherscan-data
                description: Query Ethereum gas and block data
                ---
                # Etherscan Skill
                Inspect EVM transactions and gas oracle.
            """),
            encoding="utf-8",
        )

        mock_resolver = OpenClawResolver(cache_root=cache_dir)
        monkeypatch.setattr(
            "openjarvis.tools.clawhub_tools._resolve_all_clawhub_skills",
            lambda resolver=None: _resolve_all_clawhub_skills(resolver=mock_resolver),
        )

        install_tool = ClawHubInstallTool()
        res = install_tool.execute(skill_name="etherscan-data", force=True)
        assert res.success is True
        assert ToolRegistry.contains("etherscan-data")

    def test_clawhub_list_installed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            "openjarvis.tools.clawhub_tools.get_config_dir", lambda: tmp_path
        )

        # Pre-populate one installed skill directory
        installed_dir = tmp_path / "skills" / "openclaw" / "installed-tool"
        installed_dir.mkdir(parents=True)
        (installed_dir / "SKILL.md").write_text(
            "---\nname: installed-tool\n---", encoding="utf-8"
        )

        list_tool = ClawHubListInstalledTool()
        res = list_tool.execute()
        assert res.success is True
        data = json.loads(res.content)
        assert "installed-tool" in data["installed_skills"]

    def test_subagent_auto_load_flow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        reset_subagent_manager()
        monkeypatch.setattr(
            "openjarvis.tools.clawhub_tools.get_config_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "openjarvis.skills.importer.get_config_dir", lambda: tmp_path
        )

        from openjarvis.agents.subagents import get_subagent_manager

        mgr = get_subagent_manager()

        # Runner where subagent dynamically installs a skill and checks its tools
        def autonomous_subagent_runner(record):
            search_tool = ClawHubSearchTool()
            search_res = search_tool.execute(query="slack")
            assert search_res.success is True

            install_tool = ClawHubInstallTool()
            install_res = install_tool.execute(
                skill_name="slack-notify", subagent_id=record.id, force=True
            )
            assert install_res.success is True

            # Verify subagent record got permission granted for slack-notify
            assert "slack-notify" in record.tools

            # Run newly auto-loaded tool
            loaded_tool = ToolRegistry.create("slack-notify")
            tool_res = loaded_tool.execute(task="Post status to #deployments")
            return f"Executed new tool: {tool_res.content}"

        mgr.set_dependencies(agent_runner=autonomous_subagent_runner)

        record = mgr.spawn(
            task="Find a Slack notification skill on ClawHub and use it.",
            name="Autonomous Integrator",
            wait=True,
        )

        assert record.status == "completed"
        assert "Executed new tool" in record.result
        assert "slack-notify" in record.tools
