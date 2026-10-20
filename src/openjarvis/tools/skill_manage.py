"""SkillManageTool — create, list, load, patch, rollback, or delete agent-authored skills.

Extended with Hermes-style mutation audit ledger, content-addressed snapshots,
patching (search-and-replace or rewrite), and atomic rollbacks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.skills.ledger import SkillLedger
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("skill_manage")
class SkillManageTool(BaseTool):
    """Manage agent-authored procedural skills with versioning and rollback."""

    def __init__(self, skills_dir: Path | str | None = None) -> None:
        if skills_dir is None:
            skills_dir = get_config_dir() / "skills"
        self._skills_dir = Path(skills_dir).expanduser()
        self._ledger = SkillLedger(skills_dir=self._skills_dir)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="skill_manage",
            description=(
                "Create, list, load, patch, rollback, inspect, or delete agent-authored skills. "
                "Supports in-place patching with audit logging, history tracking, and rollback."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "create",
                            "list",
                            "load",
                            "delete",
                            "patch",
                            "rollback",
                            "history",
                            "inspect",
                        ],
                        "description": "Action to perform.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (for create/load/delete/patch/rollback/history/inspect).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Skill description (for create) or patch summary description.",
                    },
                    "steps": {
                        "type": "array",
                        "description": (
                            "List of step dicts with tool_name and optional"
                            " arguments_template (for create)."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content (for rewrite patch).",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to find and replace in the skill file (for patch).",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text (for patch).",
                    },
                    "entry_id": {
                        "type": "string",
                        "description": "Specific ledger mutation ID to rollback (optional, defaults to latest).",
                    },
                },
                "required": ["action"],
            },
            category="skill",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "list")
        name = params.get("name", "")
        if action == "create":
            return self._create(
                name,
                params.get("description", ""),
                params.get("steps", []),
                author=params.get("author", "agent"),
            )
        elif action == "list":
            return self._list()
        elif action == "load":
            return self._load(name)
        elif action == "delete":
            return self._delete(name, author=params.get("author", "agent"))
        elif action == "patch":
            return self._patch(
                name,
                old_string=params.get("old_string"),
                new_string=params.get("new_string"),
                content=params.get("content"),
                description=params.get("description", ""),
                author=params.get("author", "agent"),
            )
        elif action == "rollback":
            return self._rollback(name, entry_id=params.get("entry_id"))
        elif action == "history":
            return self._history(name)
        elif action == "inspect":
            return self._inspect(name)

        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )

    def _locate_skill_target(self, name: str) -> tuple[Optional[Path], Optional[Path]]:
        """Return (target_file, target_dir) for a skill."""
        cand_toml = self._skills_dir / f"{name}.toml"
        cand_dir = self._skills_dir / name
        cand_md = cand_dir / "SKILL.md"
        cand_dir_toml = cand_dir / "skill.toml"

        if cand_toml.exists():
            return cand_toml, self._skills_dir
        if cand_md.exists():
            return cand_md, cand_dir
        if cand_dir_toml.exists():
            return cand_dir_toml, cand_dir
        if cand_dir.exists():
            return cand_dir, cand_dir
        return None, None

    def _create(
        self,
        name: str,
        description: str,
        steps: List[dict],
        author: str = "agent",
    ) -> ToolResult:
        if not name:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Skill name is required.",
            )
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        path = self._skills_dir / f"{name}.toml"

        before_snap = (
            self._ledger.capture_snapshot(self._skills_dir) if path.exists() else {}
        )

        lines = [
            "[skill]",
            f'name = "{name}"',
            f'description = "{description}"',
            "",
        ]
        for step in steps:
            lines.append("[[skill.steps]]")
            lines.append(f'tool_name = "{step.get("tool_name", "")}"')
            if "arguments_template" in step:
                lines.append(f"arguments_template = '{step['arguments_template']}'")
            if "output_key" in step:
                lines.append(f'output_key = "{step["output_key"]}"')
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        after_snap = self._ledger.capture_snapshot(self._skills_dir)

        rec = self._ledger.record_mutation(
            skill_name=name,
            action="create",
            before_manifest=before_snap,
            after_manifest=after_snap,
            description=f"Created skill: {name}",
            author=author,
        )

        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Created skill: {name} (mutation_id: {rec.id})",
        )

    def _list(self) -> ToolResult:
        if not self._skills_dir.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="No skills directory found.",
            )
        skills = []
        for f in sorted(self._skills_dir.glob("*.toml")):
            skills.append(f.stem)
        for d in sorted(self._skills_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                if (d / "SKILL.md").exists() or (d / "skill.toml").exists():
                    skills.append(d.name)

        unique_skills = sorted(list(set(skills)))
        if not unique_skills:
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="No skills found.",
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content="Available skills:\n" + "\n".join(f"- {s}" for s in unique_skills),
        )

    def _load(self, name: str) -> ToolResult:
        target_file, _ = self._locate_skill_target(name)
        if target_file is None or not target_file.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Skill not found: {name}",
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=target_file.read_text(encoding="utf-8"),
        )

    def _patch(
        self,
        name: str,
        *,
        old_string: Optional[str] = None,
        new_string: Optional[str] = None,
        content: Optional[str] = None,
        description: str = "",
        author: str = "agent",
    ) -> ToolResult:
        if not name:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Skill name is required for patch.",
            )

        target_file, target_dir = self._locate_skill_target(name)
        if target_file is None or not target_file.exists() or target_file.is_dir():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Skill not found to patch: {name}",
            )

        current_content = target_file.read_text(encoding="utf-8")
        if old_string is not None and new_string is not None:
            if old_string not in current_content:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"old_string not found in skill file '{target_file.name}'.",
                )
            patched_content = current_content.replace(old_string, new_string, 1)
        elif content is not None:
            patched_content = content
        else:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Either (old_string and new_string) or content must be provided to patch.",
            )

        # Preflight validation: if TOML, ensure valid syntax
        if target_file.suffix == ".toml":
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib
            try:
                tomllib.loads(patched_content)
            except Exception as e:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"Patch rejected: invalid TOML syntax ({e})",
                )

        snap_target = target_dir if target_dir is not None else self._skills_dir
        before_snap = self._ledger.capture_snapshot(snap_target)

        target_file.write_text(patched_content, encoding="utf-8")
        after_snap = self._ledger.capture_snapshot(snap_target)

        rec = self._ledger.record_mutation(
            skill_name=name,
            action="patch",
            before_manifest=before_snap,
            after_manifest=after_snap,
            description=description or f"Patched {target_file.name}",
            author=author,
        )

        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Successfully patched skill '{name}' (mutation_id: {rec.id}).",
        )

    def _rollback(
        self,
        name: str,
        entry_id: Optional[str] = None,
    ) -> ToolResult:
        if not name and not entry_id:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Skill name or entry_id is required for rollback.",
            )

        _, target_dir = self._locate_skill_target(name) if name else (None, None)
        if entry_id:
            ok = self._ledger.rollback_entry(entry_id, target_dir=target_dir)
            if ok:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"Successfully rolled back mutation {entry_id}.",
                )
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Failed to rollback mutation {entry_id}.",
            )

        ok = self._ledger.rollback_latest(name, target_dir=target_dir)
        if ok:
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content=f"Successfully rolled back latest mutation for skill '{name}'.",
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"No eligible mutation found to rollback for '{name}'.",
        )

    def _history(self, name: str) -> ToolResult:
        records = self._ledger.get_history(skill_name=name if name else None, limit=20)
        if not records:
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content=f"No mutation history found for '{name}'."
                if name
                else "No mutation history found.",
            )

        lines = [
            f"Mutation history for '{name}':"
            if name
            else "Global skill mutation history:"
        ]
        for r in records:
            lines.append(
                f"- [{r.id}] {r.action.upper()} | {r.skill_name} | by {r.author} | {r.description}"
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content="\n".join(lines),
        )

    def _inspect(self, name: str) -> ToolResult:
        target_file, target_dir = self._locate_skill_target(name)
        if target_file is None or not target_file.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Skill '{name}' not found.",
            )

        info: dict[str, Any] = {
            "name": name,
            "target_path": str(target_file),
            "is_dir": target_file.is_dir(),
        }
        if target_file.is_file():
            info["content"] = target_file.read_text(encoding="utf-8")
        history = self._ledger.get_history(skill_name=name, limit=5)
        info["recent_mutations"] = [r.to_dict() for r in history]

        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=json.dumps(info, indent=2),
        )

    def _delete(self, name: str, author: str = "agent") -> ToolResult:
        target_file, target_dir = self._locate_skill_target(name)
        if target_file is None or not target_file.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Skill not found: {name}",
            )

        snap_target = target_dir if target_dir is not None else self._skills_dir
        before_snap = self._ledger.capture_snapshot(snap_target)

        import shutil

        if target_file.is_dir():
            shutil.rmtree(target_file)
        else:
            target_file.unlink()

        self._ledger.record_mutation(
            skill_name=name,
            action="delete",
            before_manifest=before_snap,
            after_manifest={},
            description=f"Deleted skill: {name}",
            author=author,
        )

        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Deleted skill: {name}",
        )
