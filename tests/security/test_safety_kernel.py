"""Focused test suite for Ultron Safety Kernel, Risk Levels, Safety Code, and Custom Safety Rules."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from openjarvis.security.file_policy import validate_ultron_fs_operation
from openjarvis.security.kernel import (
    ActionEffect,
    CustomRule,
    CustomRuleEngine,
    RiskLevel,
    SafetyCodeManager,
    SafetyDecision,
    SafetyKernel,
    get_safety_kernel,
)


@pytest.fixture
def temp_code_manager(tmp_path: Path) -> SafetyCodeManager:
    """Fixture providing a SafetyCodeManager isolated to tmp_path."""
    storage = tmp_path / "safety_code.json"
    return SafetyCodeManager(storage_path=storage)


@pytest.fixture
def temp_rules_engine(tmp_path: Path) -> CustomRuleEngine:
    """Fixture providing a CustomRuleEngine isolated to tmp_path."""
    storage = tmp_path / "safety_rules.json"
    return CustomRuleEngine(storage_path=storage)


@pytest.fixture
def isolated_kernel(tmp_path: Path) -> SafetyKernel:
    """Fixture providing a fully isolated SafetyKernel instance."""
    kernel = SafetyKernel()
    kernel.code_mgr = SafetyCodeManager(storage_path=tmp_path / "safety_code.json")
    kernel.rules_engine = CustomRuleEngine(storage_path=tmp_path / "safety_rules.json")
    return kernel


# ---------------------------------------------------------------------------
# 1. Safety Code & Password-Hashing Tests
# ---------------------------------------------------------------------------

class TestSafetyCodeManager:
    def test_code_lifecycle(self, temp_code_manager: SafetyCodeManager) -> None:
        """Test setting, verifying, and updating the safety code."""
        assert not temp_code_manager.is_code_set()

        # Reject short code (<4 chars)
        ok, msg = temp_code_manager.set_safety_code("123")
        assert not ok
        assert "at least 4 characters" in msg

        # Set valid code
        ok, msg = temp_code_manager.set_safety_code("SecureCode123!")
        assert ok
        assert temp_code_manager.is_code_set()

        # Verify correct and incorrect codes
        assert temp_code_manager.verify_safety_code("SecureCode123!")
        assert not temp_code_manager.verify_safety_code("WrongCode")
        assert not temp_code_manager.verify_safety_code("")

        # Updating code requires old code verification
        ok, msg = temp_code_manager.set_safety_code("NewCode456!", old_code="WrongOld")
        assert not ok

        ok, msg = temp_code_manager.set_safety_code("NewCode456!", old_code="SecureCode123!")
        assert ok
        assert temp_code_manager.verify_safety_code("NewCode456!")
        assert not temp_code_manager.verify_safety_code("SecureCode123!")

    def test_single_use_action_token_lifecycle(self, temp_code_manager: SafetyCodeManager) -> None:
        """Test token creation, consumption, and single-use enforcement."""
        fp = temp_code_manager.compute_fingerprint("file_delete", "D:\\Projects\\old.tmp")
        token = temp_code_manager.generate_action_token(fp, ttl_seconds=60.0)

        # 1. First consumption succeeds
        valid, msg = temp_code_manager.consume_action_token(token, fp)
        assert valid
        assert "Authorization confirmed" in msg

        # 2. Second consumption fails (single-use)
        valid2, msg2 = temp_code_manager.consume_action_token(token, fp)
        assert not valid2
        assert "already been consumed" in msg2

    def test_token_invalidation_on_target_tamper(self, temp_code_manager: SafetyCodeManager) -> None:
        """Approval must invalidate if the action targets or parameters change."""
        orig_fp = temp_code_manager.compute_fingerprint("file_delete", "D:\\Projects\\safe.txt")
        token = temp_code_manager.generate_action_token(orig_fp, ttl_seconds=60.0)

        tampered_fp = temp_code_manager.compute_fingerprint("file_delete", "C:\\Windows\\system32\\cmd.exe")
        valid, msg = temp_code_manager.consume_action_token(token, tampered_fp)
        assert not valid
        assert "mismatch" in msg.lower()

    def test_token_expiration(self, temp_code_manager: SafetyCodeManager) -> None:
        """Token must expire when TTL is exceeded."""
        fp = temp_code_manager.compute_fingerprint("file_delete", "D:\\Projects\\sample.txt")
        token = temp_code_manager.generate_action_token(fp, ttl_seconds=0.01)
        time.sleep(0.02)

        valid, msg = temp_code_manager.consume_action_token(token, fp)
        assert not valid
        assert "expired" in msg.lower()


# ---------------------------------------------------------------------------
# 2. Custom Safety Rules & Plain Language Compiler Tests
# ---------------------------------------------------------------------------

class TestCustomRuleEngine:
    def test_plain_language_rule_compiler(self, temp_rules_engine: CustomRuleEngine) -> None:
        """Convert natural language instructions into structured rules."""
        # 1. Deny C:\Windows
        rules1 = temp_rules_engine.compile_plain_language(
            "Ultron can read the C drive but cannot modify or delete files inside C:\\Windows."
        )
        assert len(rules1) >= 2
        effects = {r.effect for r in rules1}
        assert "DENY" in effects
        assert "ALLOW" in effects

        deny_r = next(r for r in rules1 if r.effect == "DENY")
        assert "windows" in deny_r.path_pattern.lower()

        # 2. Allow writes to D:\Projects
        rules2 = temp_rules_engine.compile_plain_language(
            "Ultron can create and edit files inside D:\\Projects."
        )
        assert len(rules2) == 1
        assert rules2[0].effect == "ALLOW"
        assert "projects" in rules2[0].path_pattern.lower()

        # 3. Ask permission before deleting files
        rules3 = temp_rules_engine.compile_plain_language(
            "Ask my permission before deleting files elsewhere."
        )
        assert len(rules3) == 1
        assert rules3[0].effect == "ASK"

    def test_rule_precedence_deny_over_allow(self, temp_rules_engine: CustomRuleEngine) -> None:
        """Explicit DENY rules must strictly take precedence over ALLOW rules."""
        # Add an ALLOW rule for all of D:\*
        temp_rules_engine.add_rule(
            CustomRule(
                id="allow_d",
                raw_text="Allow all D drive",
                effect="ALLOW",
                action_types=["write"],
                path_pattern="D:\\*",
            )
        )

        # Add a DENY rule for D:\Sensitive\*
        temp_rules_engine.add_rule(
            CustomRule(
                id="deny_sensitive",
                raw_text="Deny D:\\Sensitive",
                effect="DENY",
                action_types=["write"],
                path_pattern="D:\\Sensitive\\*",
            )
        )

        # Target inside D:\Sensitive -> DENY wins
        effect, rule = temp_rules_engine.evaluate("file_write", "D:\\Sensitive\\doc.txt")
        assert effect == "DENY"
        assert rule.id == "deny_sensitive"

        # Target in D:\Other -> ALLOW wins
        effect, rule = temp_rules_engine.evaluate("file_write", "D:\\Other\\doc.txt")
        assert effect == "ALLOW"
        assert rule.id == "allow_d"


# ---------------------------------------------------------------------------
# 3. Four Practical Risk Levels & Platform Security Invariants
# ---------------------------------------------------------------------------

class TestSafetyKernelEnforcement:
    def test_critical_hard_blocks_cannot_be_overridden(self, isolated_kernel: SafetyKernel) -> None:
        """Dangerous actions (format, C:\\Windows modification) are CRITICAL and hard-blocked."""
        # 1. Formatting drive
        dec_fmt = isolated_kernel.evaluate("shell_exec", target="format C: /fs:NTFS")
        assert dec_fmt.risk_level == RiskLevel.CRITICAL
        assert dec_fmt.effect == ActionEffect.BLOCK
        assert dec_fmt.is_blocked

        # 2. Modifying C:\Windows files
        dec_win = isolated_kernel.evaluate("file_write", target="C:\\Windows\\System32\\drivers\\etc\\hosts")
        assert dec_win.risk_level == RiskLevel.CRITICAL
        assert dec_win.effect == ActionEffect.BLOCK

        # Even with an active safety code, critical operations must remain blocked
        isolated_kernel.code_mgr.set_safety_code("MasterCode123!")
        dec_win2 = isolated_kernel.evaluate("file_delete", target="C:\\Windows\\explorer.exe")
        assert dec_win2.risk_level == RiskLevel.CRITICAL
        assert dec_win2.effect == ActionEffect.BLOCK

    def test_high_risk_deletions_require_code(self, isolated_kernel: SafetyKernel) -> None:
        """File deletion is HIGH risk and requires safety code when configured."""
        # Without safety code set
        dec_no_code = isolated_kernel.evaluate("file_delete", target="D:\\Projects\\scratch.log")
        assert dec_no_code.risk_level == RiskLevel.HIGH
        assert dec_no_code.effect == ActionEffect.ASK

        # With safety code configured
        isolated_kernel.code_mgr.set_safety_code("Passcode123!")
        dec_with_code = isolated_kernel.evaluate("file_delete", target="D:\\Projects\\scratch.log")
        assert dec_with_code.risk_level == RiskLevel.HIGH
        assert dec_with_code.effect == ActionEffect.ASK_WITH_CODE
        assert dec_with_code.requires_code is True

    def test_low_and_medium_risk_actions(self, isolated_kernel: SafetyKernel) -> None:
        """Low risk actions execute automatically."""
        dec_read = isolated_kernel.evaluate("file_read", target="D:\\data\\report.csv")
        assert dec_read.risk_level == RiskLevel.LOW
        assert dec_read.is_allowed

        dec_app = isolated_kernel.evaluate("app_launch", target="notepad.exe")
        assert dec_app.risk_level == RiskLevel.LOW
        assert dec_app.is_allowed


# ---------------------------------------------------------------------------
# 4. Central Enforcement & Tool Bypass Prevention Tests
# ---------------------------------------------------------------------------

class TestCentralEnforcement:
    def test_validate_ultron_fs_operation_wired_to_kernel(self, tmp_path: Path) -> None:
        """Test validate_ultron_fs_operation intercepts via Safety Kernel."""
        # 1. Sensitive file is blocked
        valid, msg = validate_ultron_fs_operation(".env", operation="read")
        assert not valid
        assert "sensitive credential" in msg

        # 2. Deletion without token is blocked/requires approval
        valid, msg = validate_ultron_fs_operation("D:\\test.txt", operation="delete")
        assert not valid
        assert "Destructive Action" in msg or "Approval Required" in msg

    def test_safe_quarantine_fallback(self, tmp_path: Path, isolated_kernel: SafetyKernel) -> None:
        """Test safe deletion fallback to quarantine when Recycle Bin is unavailable or fails."""
        test_file = tmp_path / "obsolete.txt"
        test_file.write_text("sample content to delete", encoding="utf-8")
        assert test_file.exists()

        # Patch sys.platform so it tests the quarantine fallback cleanly
        with patch("sys.platform", "linux"):
            ok, msg = isolated_kernel.safe_delete_or_quarantine(test_file)
            assert ok
            assert not test_file.exists()
            assert "quarantine" in msg.lower()

    def test_cleanup_preview_calculation(self, tmp_path: Path, isolated_kernel: SafetyKernel) -> None:
        """Test cleanup impact preview calculation."""
        f1 = tmp_path / "file1.log"
        f1.write_text("abc", encoding="utf-8")  # 3 bytes
        f2 = tmp_path / "file2.log"
        f2.write_text("12345", encoding="utf-8")  # 5 bytes

        preview = isolated_kernel.preview_cleanup([str(f1), str(f2)])
        assert preview["total_files"] == 2
        assert preview["total_bytes"] == 8
        assert "destination" in preview


# ---------------------------------------------------------------------------
# 5. REST API Integration Tests (/api/safety/*)
# ---------------------------------------------------------------------------

class TestSafetyRoutesAPI:
    @pytest.fixture
    def client(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from openjarvis.server.safety_routes import safety_router

        # Patch global kernel storage to tmp_path for test isolation
        kernel = get_safety_kernel()
        kernel.code_mgr.storage_path = tmp_path / "safety_code.json"
        kernel.code_mgr._tokens.clear()
        kernel.rules_engine.storage_path = tmp_path / "safety_rules.json"
        kernel.rules_engine._rules.clear()

        app = FastAPI()
        app.include_router(safety_router)
        return TestClient(app)

    def test_api_status_and_code_flow(self, client) -> None:
        # Initial status
        res = client.get("/api/safety/status")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["rules_count"] == 0

        # Set safety code
        res_set = client.post("/api/safety/code/set", json={"code": "Pass1234!"})
        assert res_set.status_code == 200
        assert res_set.json()["success"] is True

        # Status reflects configured
        res_stat = client.get("/api/safety/status")
        assert res_stat.json()["configured"] is True

        # Verify incorrect code
        res_bad = client.post(
            "/api/safety/code/verify",
            json={
                "code": "WrongCode",
                "action_type": "file_delete",
                "target": "D:\\Projects\\old.log",
            },
        )
        assert res_bad.status_code == 200
        assert res_bad.json()["valid"] is False

        # Verify correct code -> yields single-use action token
        res_good = client.post(
            "/api/safety/code/verify",
            json={
                "code": "Pass1234!",
                "action_type": "file_delete",
                "target": "D:\\Projects\\old.log",
            },
        )
        assert res_good.status_code == 200
        auth = res_good.json()
        assert auth["valid"] is True
        assert auth["token"].startswith("sat_")
        assert "fingerprint" in auth

    def test_api_rules_compile_and_save(self, client) -> None:
        # Compile preview
        res_comp = client.post(
            "/api/safety/rules/compile",
            json={"instruction": "Ultron can read C drive but cannot delete inside C:\\Windows"},
        )
        assert res_comp.status_code == 200
        preview = res_comp.json()
        assert "preview_rules" in preview
        assert len(preview["preview_rules"]) >= 1

        # Save approved rules
        rules_to_save = preview["preview_rules"]
        res_save = client.post("/api/safety/rules/save", json={"rules": rules_to_save})
        assert res_save.status_code == 200
        assert res_save.json()["success"] is True

        # List saved rules
        res_list = client.get("/api/safety/rules")
        assert res_list.status_code == 200
        saved_list = res_list.json()["rules"]
        assert len(saved_list) == len(rules_to_save)

        # Delete a rule
        rule_id = saved_list[0]["id"]
        res_del = client.delete(f"/api/safety/rules/{rule_id}")
        assert res_del.status_code == 200
        assert res_del.json()["success"] is True

    def test_api_cleanup_preview_and_execute(self, client, tmp_path: Path) -> None:
        target = tmp_path / "junk.txt"
        target.write_text("temporary data", encoding="utf-8")

        # Set code
        client.post("/api/safety/code/set", json={"code": "CleanPass123!"})

        # Preview
        res_prev = client.post("/api/safety/cleanup/preview", json={"targets": [str(target)]})
        assert res_prev.status_code == 200
        assert res_prev.json()["preview"]["total_files"] == 1

        # Verify and get token
        res_tok = client.post(
            "/api/safety/code/verify",
            json={
                "code": "CleanPass123!",
                "action_type": "delete",
                "target": str(target),
            },
        )
        token = res_tok.json()["token"]

        # Execute safe delete
        with patch("sys.platform", "linux"):
            res_exec = client.post(
                "/api/safety/cleanup/execute",
                json={"target": str(target), "token": token},
            )
            assert res_exec.status_code == 200
            assert res_exec.json()["success"] is True
            assert not target.exists()

