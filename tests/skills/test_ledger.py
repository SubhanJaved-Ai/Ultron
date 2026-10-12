"""Tests for SkillLedger: mutation audit logging, blob storage, and atomic rollbacks."""

from pathlib import Path

from openjarvis.skills.ledger import SkillLedger


def test_ledger_creation_and_recording(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    ledger = SkillLedger(skills_dir=skills_dir)

    # Create dummy skill file
    skill_file = skills_dir / "test_skill.toml"
    skill_file.write_text('[skill]\nname = "test_skill"\n', encoding="utf-8")

    snap = ledger.capture_snapshot(skills_dir)
    assert "test_skill.toml" in snap

    rec = ledger.record_mutation(
        skill_name="test_skill",
        action="create",
        before_manifest={},
        after_manifest=snap,
        description="Initial creation",
    )
    assert rec.id
    assert rec.action == "create"
    assert rec.skill_name == "test_skill"

    history = ledger.get_history(skill_name="test_skill")
    assert len(history) == 1
    assert history[0].id == rec.id


def test_ledger_patch_and_rollback(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    ledger = SkillLedger(skills_dir=skills_dir)

    skill_file = skills_dir / "my_skill.toml"
    skill_file.write_text('v1 = "initial"\n', encoding="utf-8")

    snap_v1 = ledger.capture_snapshot(skills_dir)
    rec_v1 = ledger.record_mutation(
        skill_name="my_skill",
        action="create",
        before_manifest={},
        after_manifest=snap_v1,
    )

    # Patch skill
    skill_file.write_text('v1 = "modified"\n', encoding="utf-8")
    snap_v2 = ledger.capture_snapshot(skills_dir)
    rec_v2 = ledger.record_mutation(
        skill_name="my_skill",
        action="patch",
        before_manifest=snap_v1,
        after_manifest=snap_v2,
        description="Updated to modified",
    )
    assert rec_v1.id and rec_v2.id

    assert skill_file.read_text(encoding="utf-8") == 'v1 = "modified"\n'

    # Rollback latest mutation
    ok = ledger.rollback_latest("my_skill")
    assert ok is True
    assert skill_file.read_text(encoding="utf-8") == 'v1 = "initial"\n'

    # Verify rollback recorded in history
    history = ledger.get_history("my_skill")
    assert len(history) == 3
    assert history[0].action == "rollback"
