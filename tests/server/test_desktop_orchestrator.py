"""Unit tests for Ultron Desktop Agent Orchestrator & System Catalog RAG."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from openjarvis.desktop.catalog_rag import SystemCatalogRAG, SystemItem
from openjarvis.desktop.orchestrator import (
    DesktopDirectiveResult,
    DesktopOrchestrator,
    DesktopSafetyGuardrails,
)
from openjarvis.server.app import create_app


def _make_mock_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


class TestSystemCatalogRAG:
    def test_catalog_indexing(self):
        catalog = SystemCatalogRAG(cache_ttl_seconds=600)
        catalog.ensure_indexed(force=True)
        assert len(catalog._items) > 0

    def test_catalog_find_chrome_profile_airluc(self):
        catalog = SystemCatalogRAG()
        catalog.ensure_indexed()
        profile = catalog.find_chrome_profile("airluc")
        assert profile is not None
        assert profile.item_type == "chrome_profile"
        assert "Profile 10" in profile.arguments or "Profile 10" in profile.id or "airluc" in profile.name.lower()

    def test_catalog_find_drives_and_folders(self):
        catalog = SystemCatalogRAG()
        catalog.ensure_indexed()

        this_pc = catalog.find_folder_or_drive("my computer")
        assert this_pc is not None
        assert "shell:MyComputerFolder" in this_pc.target_path or "Computer" in this_pc.name

        d_drive = catalog.find_folder_or_drive("d drive")
        assert d_drive is not None
        assert "D:" in d_drive.target_path.upper()

        save_folder = catalog.find_folder_or_drive("save folder")
        assert save_folder is not None
        assert "Downloads" in save_folder.target_path or "save" in save_folder.name.lower()


class TestDesktopSafetyGuardrails:
    def test_zero_deletion_blocks_delete_directives(self):
        safe, msg = DesktopSafetyGuardrails.check_deletion("delete the file on D drive")
        assert not safe
        assert "Zero-Data-Loss" in msg

        safe2, _ = DesktopSafetyGuardrails.check_deletion("rm -rf /")
        assert not safe2

        safe3, _ = DesktopSafetyGuardrails.check_deletion("erase this video")
        assert not safe3

    def test_safe_directives_pass_deletion_check(self):
        safe, _ = DesktopSafetyGuardrails.check_deletion("open my computer")
        assert safe

        safe2, _ = DesktopSafetyGuardrails.check_deletion("open airluc chrome and search youtube.com")
        assert safe2

    def test_url_scheme_safety(self):
        safe, msg = DesktopSafetyGuardrails.check_url_safety("https://www.youtube.com")
        assert safe

        unsafe, msg = DesktopSafetyGuardrails.check_url_safety("javascript:alert(1)")
        assert not unsafe
        assert "blocked" in msg.lower()

    def test_ordinary_non_deletion_directives_not_incorrectly_gated(self):
        """1. Ordinary non-deletion directives are not incorrectly routed through destructive-deletion authorization."""
        safe, msg = DesktopSafetyGuardrails.check_deletion("open spotify and play jazz music")
        assert safe
        assert msg == ""

        safe2, msg2 = DesktopSafetyGuardrails.check_deletion("browse to google.com and find recipes")
        assert safe2
        assert msg2 == ""

        safe3, msg3 = DesktopSafetyGuardrails.check_deletion("show me system statistics and memory usage")
        assert safe3
        assert msg3 == ""

    def test_actual_deletion_requests_remain_protected(self):
        """2. Actual deletion requests remain protected by the required safety checks."""
        for kw in ["delete", "remove", "erase", "destroy", "del", "rm", "unlink", "format", "drop", "killall"]:
            safe, msg = DesktopSafetyGuardrails.check_deletion(f"{kw} user records now")
            assert not safe, f"Keyword '{kw}' must be caught by deletion guardrail"
            assert len(msg) > 0

    def test_unauthorized_destructive_actions_gated_by_kernel_effects(self):
        """3. Unauthorized destructive actions are still rejected or gated correctly across ASK, ASK_WITH_CODE, BLOCK."""
        from openjarvis.security.kernel import ActionEffect, RiskLevel, SafetyDecision

        with patch("openjarvis.security.kernel.get_safety_kernel") as mock_get_kernel:
            kernel_mock = MagicMock()
            mock_get_kernel.return_value = kernel_mock

            # BLOCK effect
            kernel_mock.evaluate.return_value = SafetyDecision(
                effect=ActionEffect.BLOCK,
                risk_level=RiskLevel.HIGH,
                reason="Direct deletion of files is blocked by risk policy.",
                action_type="delete",
                target="important_document.txt",
            )
            safe_block, msg_block = DesktopSafetyGuardrails.check_deletion("rm important_document.txt")
            assert not safe_block
            assert "blocked" in msg_block.lower()

            # ASK effect
            kernel_mock.evaluate.return_value = SafetyDecision(
                effect=ActionEffect.ASK,
                risk_level=RiskLevel.HIGH,
                reason="Confirmation required before deleting resource.",
                action_type="delete",
                target="database table",
            )
            safe_ask, msg_ask = DesktopSafetyGuardrails.check_deletion("delete database table")
            assert not safe_ask
            assert "confirmation required" in msg_ask.lower()

            # ASK_WITH_CODE effect
            kernel_mock.evaluate.return_value = SafetyDecision(
                effect=ActionEffect.ASK_WITH_CODE,
                risk_level=RiskLevel.HIGH,
                reason="Safety code required for deletion authorization.",
                action_type="delete",
                target="system backup",
            )
            safe_code, msg_code = DesktopSafetyGuardrails.check_deletion("erase system backup")
            assert not safe_code
            assert "safety code" in msg_code.lower()

    def test_safety_kernel_errors_fail_closed(self):
        """4. Errors and missing context do not silently authorize destructive actions."""
        with patch("openjarvis.security.kernel.get_safety_kernel") as mock_get_kernel:
            mock_get_kernel.side_effect = RuntimeError("Safety kernel database unreachable")
            safe, msg = DesktopSafetyGuardrails.check_deletion("format drive C:")
            assert not safe
            assert "Safety verification failed" in msg


class TestDesktopOrchestrator:
    @patch("subprocess.Popen")
    def test_handle_chrome_profile_launch(self, mock_popen):
        orchestrator = DesktopOrchestrator()
        res = orchestrator.handle_directive("go to airluc chrome profile and search for youtube.com")
        assert res.handled
        assert res.status == "executed"
        assert res.target_type == "chrome_profile"
        assert "AirLuc" in res.reply or "AirLuc" in str(res.actions)
        assert mock_popen.called

    @patch("subprocess.Popen")
    def test_handle_explorer_my_computer(self, mock_popen):
        orchestrator = DesktopOrchestrator()
        res = orchestrator.handle_directive("open my computer")
        assert res.handled
        assert res.status == "executed"
        assert res.target_type == "shell_folder"
        assert "shell:MyComputerFolder" in str(res.target_path)
        assert mock_popen.called

    @patch("subprocess.Popen")
    def test_handle_explorer_d_drive(self, mock_popen):
        orchestrator = DesktopOrchestrator()
        res = orchestrator.handle_directive("open my D drive")
        assert res.handled
        assert res.status == "executed"
        assert res.target_type == "drive"
        assert "D:" in str(res.target_path).upper()
        assert mock_popen.called

    @patch("subprocess.Popen")
    def test_handle_explorer_e_drive(self, mock_popen):
        orchestrator = DesktopOrchestrator()
        res = orchestrator.handle_directive("open my E drive")
        assert res.handled
        assert res.status == "executed"
        assert res.target_type == "drive"
        assert "E:" in str(res.target_path).upper()
        assert mock_popen.called

    @patch("subprocess.Popen")
    def test_handle_app_launch_capcut(self, mock_popen):
        orchestrator = DesktopOrchestrator()
        res = orchestrator.handle_directive("open CapCut")
        assert res.handled
        assert res.status == "executed"
        assert res.target_type == "app"
        assert "CapCut" in res.reply

    def test_handle_deletion_blocked(self):
        orchestrator = DesktopOrchestrator()
        res = orchestrator.handle_directive("delete my file on D drive")
        assert res.handled
        assert res.status == "guardrail_blocked"
        assert "Zero-Data-Loss" in res.reply


class TestHologramIntegrationWithDesktopOrchestrator:
    @patch("subprocess.Popen")
    def test_hologram_directive_delegates_to_desktop_orchestrator(self, mock_popen):
        engine = _make_mock_engine()
        app = create_app(engine, "test-model")
        client = TestClient(app)

        # Chrome profile test
        resp = client.post("/api/hologram/directive", json={"directive": "open airluc chrome and go to youtube.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "executed"
        assert len(data.get("actions", [])) >= 1
        assert data["actions"][0]["name"] == "chrome_profile_navigate"

        # Explorer test: My Computer
        resp2 = client.post("/api/hologram/directive", json={"directive": "open my computer"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("status") == "executed"
        assert data2["actions"][0]["name"] == "open_folder" or data2["actions"][0]["name"] == "open_drive"

        # App launch test: CapCut
        resp3 = client.post("/api/hologram/directive", json={"directive": "open CapCut"})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3.get("status") == "executed"
        assert data3["actions"][0]["name"] == "app_launch"
