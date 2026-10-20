"""Deterministic tests for file sandbox operations, path traversal protections,
UTF-8 byte fidelity, patch application, and security approval gating.

Covers:
1. Create new text file through file_write.
2. Read back content through file_read.
3. Edit file through apply_patch with unified diff.
4. Verify exact bytes and UTF-8 content on disk.
5. Gracefully handle nonexistent paths.
6. Reject path traversal attempts outside permitted sandbox directory.
7. Verify approval gating and blocking for protected / sensitive operations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openjarvis.security.file_policy import is_sensitive_file, validate_ultron_fs_operation
from openjarvis.security.kernel import CustomRule, RiskLevel, get_safety_kernel
from openjarvis.tools.apply_patch import ApplyPatchTool
from openjarvis.tools.file_read import FileReadTool
from openjarvis.tools.file_write import FileWriteTool


class TestFileSandboxReliability:
    def test_sandbox_file_lifecycle_write_read_patch_verify(self, tmp_path: Path) -> None:
        """End-to-end lifecycle: Write, Read, Patch, and verify exact UTF-8 bytes on disk."""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        allowed = [str(sandbox_dir)]

        writer = FileWriteTool(allowed_dirs=allowed)
        reader = FileReadTool(allowed_dirs=allowed)
        patcher = ApplyPatchTool()

        target_file = sandbox_dir / "quantum_core.py"

        initial_content = (
            "# Quantum Core Subsystem\n"
            "STATUS = 'INITIALIZING'\n"
            "CAPACITY = 100\n"
            "NAME = 'Ultron-Argon'\n"
        )

        # 1. Create file through file_write
        write_result = writer.execute(
            path=str(target_file),
            content=initial_content,
            mode="write",
            create_dirs=True,
        )
        assert write_result.success is True, f"file_write failed: {write_result.content}"
        assert target_file.exists()

        # 2. Read back through file_read
        read_result = reader.execute(path=str(target_file))
        assert read_result.success is True
        assert read_result.content == initial_content

        # 3. Edit file through apply_patch
        diff_patch = (
            "--- a/quantum_core.py\n"
            "+++ b/quantum_core.py\n"
            "@@ -1,4 +1,4 @@\n"
            " # Quantum Core Subsystem\n"
            "-STATUS = 'INITIALIZING'\n"
            "+STATUS = 'OPERATIONAL'\n"
            " CAPACITY = 100\n"
            " NAME = 'Ultron-Argon'\n"
        )
        patch_result = patcher.execute(path=str(target_file), patch=diff_patch, backup=True)
        assert patch_result.success is True, f"apply_patch failed: {patch_result.content}"

        # 4. Verify exact bytes and UTF-8 content on disk
        expected_patched = (
            "# Quantum Core Subsystem\n"
            "STATUS = 'OPERATIONAL'\n"
            "CAPACITY = 100\n"
            "NAME = 'Ultron-Argon'\n"
        )
        actual_disk_bytes = target_file.read_bytes()
        # Ensure raw bytes strictly decode as valid UTF-8
        decoded_disk_text = actual_disk_bytes.decode("utf-8")
        assert decoded_disk_text.replace("\r\n", "\n") == expected_patched
        # Verify read_text handles universal newlines reliably
        assert target_file.read_text(encoding="utf-8") == expected_patched

        # Verify backup was created
        backup_file = Path(str(target_file) + ".bak")
        assert backup_file.exists()
        assert backup_file.read_text(encoding="utf-8") == initial_content

    def test_graceful_handling_of_nonexistent_path(self, tmp_path: Path) -> None:
        """file_read and apply_patch gracefully report file not found without crashing."""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        missing_file = sandbox_dir / "does_not_exist.txt"

        reader = FileReadTool(allowed_dirs=[str(sandbox_dir)])
        read_res = reader.execute(path=str(missing_file))
        assert read_res.success is False
        assert "File not found" in read_res.content

        patcher = ApplyPatchTool()
        dummy_patch = (
            "--- a/missing.txt\n"
            "+++ b/missing.txt\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        patch_res = patcher.execute(path=str(missing_file), patch=dummy_patch)
        assert patch_res.success is False
        assert "File not found" in patch_res.content

    def test_reject_path_traversal_outside_sandbox(self, tmp_path: Path) -> None:
        """Path traversal attacks (../) outside permitted sandbox are strictly blocked."""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        outside_dir = tmp_path / "outside_private"
        outside_dir.mkdir(parents=True, exist_ok=True)
        outside_file = outside_dir / "leak.txt"
        outside_file.write_text("classified data", encoding="utf-8")

        # Sandboxed tool restricted to sandbox_dir only
        reader = FileReadTool(allowed_dirs=[str(sandbox_dir)])
        writer = FileWriteTool(allowed_dirs=[str(sandbox_dir)])

        # Traversal attempt: sandbox/../outside_private/leak.txt
        traversal_read_path = str(sandbox_dir / ".." / "outside_private" / "leak.txt")
        read_res = reader.execute(path=traversal_read_path)
        assert read_res.success is False
        assert "outside allowed directories" in read_res.content

        # Traversal write attempt
        traversal_write_path = str(sandbox_dir / ".." / "outside_private" / "intruder.txt")
        write_res = writer.execute(path=traversal_write_path, content="hacked")
        assert write_res.success is False
        assert "outside allowed directories" in write_res.content
        assert not (outside_dir / "intruder.txt").exists()

    def test_sensitive_file_blocking(self, tmp_path: Path) -> None:
        """Writing or reading sensitive credentials (.env, credentials.json, id_rsa) is blocked."""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        allowed = [str(sandbox_dir)]

        writer = FileWriteTool(allowed_dirs=allowed)
        reader = FileReadTool(allowed_dirs=allowed)
        patcher = ApplyPatchTool()

        # .env protection
        env_file = sandbox_dir / ".env"
        write_res = writer.execute(
            path=str(env_file),
            content="SECRET_KEY=12345",
            create_dirs=True,
        )
        assert write_res.success is False
        assert "sensitive" in write_res.content.lower() or "guardrail" in write_res.content.lower()

        # Manually create .env to test read blocking
        env_file.write_text("SECRET=123", encoding="utf-8")
        read_res = reader.execute(path=str(env_file))
        assert read_res.success is False
        assert "sensitive" in read_res.content.lower()

        # Patch blocking on sensitive file
        patch_res = patcher.execute(
            path=str(env_file),
            patch="--- a/.env\n+++ b/.env\n@@ -1,1 +1,1 @@\n-SECRET=123\n+SECRET=456\n",
        )
        assert patch_res.success is False
        assert "sensitive" in patch_res.content.lower()

    def test_approval_gating_custom_rule(self, tmp_path: Path) -> None:
        """Safety kernel approval gating requires authorization token for protected paths."""
        kernel = get_safety_kernel()
        protected_dir = tmp_path / "protected_vault"
        protected_dir.mkdir(parents=True, exist_ok=True)

        rule_id = f"test_ask_rule_{protected_dir.name}"
        ask_rule = CustomRule(
            id=rule_id,
            raw_text="Ask permission before modifying files in vault",
            effect="ASK",
            action_types=["write", "create", "modify", "delete", "edit"],
            path_pattern=str(protected_dir / "*"),
            risk_level=RiskLevel.HIGH.value,
        )
        kernel.rules_engine.add_rule(ask_rule)

        try:
            target_path = protected_dir / "secure_data.txt"
            writer = FileWriteTool()

            # Attempt write without authorization token -> blocked by approval gate
            write_res = writer.execute(
                path=str(target_path),
                content="Unauthorized write",
                create_dirs=True,
            )
            assert write_res.success is False
            assert "Approval Required" in write_res.content

            # Evaluate decision and generate valid action token
            decision = kernel.evaluate("file_write", target=str(target_path))
            assert decision.effect.value in ("ask", "ask_with_code")
            auth_token = kernel.code_mgr.issue_action_token(decision.fingerprint)

            # Attempt write WITH valid single-use action token -> succeeds
            authorized_res = writer.execute(
                path=str(target_path),
                content="Authorized write verified",
                authorization_token=auth_token,
                create_dirs=True,
            )
            assert authorized_res.success is True, f"Expected success: {authorized_res.content}"
            assert target_path.read_text(encoding="utf-8") == "Authorized write verified"

        finally:
            kernel.rules_engine.remove_rule(rule_id)
