"""Tests for SkillManageTool extended actions: patch, rollback, history, inspect."""

from pathlib import Path

from openjarvis.tools.skill_manage import SkillManageTool


def test_skill_manage_patch_and_rollback(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    tool = SkillManageTool(skills_dir=skills_dir)

    # 1. Create skill
    res = tool.execute(
        action="create",
        name="web_fetch",
        description="Fetch a web page",
        steps=[{"tool_name": "http_request"}],
    )
    assert res.success is True
    assert "Created skill: web_fetch" in res.content

    # 2. Patch skill with search-and-replace
    res_patch = tool.execute(
        action="patch",
        name="web_fetch",
        old_string="Fetch a web page",
        new_string="Fetch a web page with retry",
        description="Add retry to description",
    )
    assert res_patch.success is True
    assert "Successfully patched skill" in res_patch.content

    # Verify content updated
    res_load = tool.execute(action="load", name="web_fetch")
    assert res_load.success is True
    assert "Fetch a web page with retry" in res_load.content

    # 3. History
    res_hist = tool.execute(action="history", name="web_fetch")
    assert res_hist.success is True
    assert "PATCH" in res_hist.content

    # 4. Rollback
    res_rb = tool.execute(action="rollback", name="web_fetch")
    assert res_rb.success is True

    # Verify rolled back
    res_load_after = tool.execute(action="load", name="web_fetch")
    assert "Fetch a web page with retry" not in res_load_after.content
    assert "Fetch a web page" in res_load_after.content


def test_skill_manage_patch_invalid_toml(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    tool = SkillManageTool(skills_dir=skills_dir)

    tool.execute(action="create", name="bad_skill", description="test")
    res_bad = tool.execute(
        action="patch",
        name="bad_skill",
        content="[skill\nname = unclosed string",
    )
    assert res_bad.success is False
    assert "invalid TOML syntax" in res_bad.content
