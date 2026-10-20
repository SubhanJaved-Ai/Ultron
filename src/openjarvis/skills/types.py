"""Skill type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class SkillStep:
    """A single step in a skill pipeline."""

    tool_name: str = ""
    skill_name: str = ""  # invoke another skill instead of a tool
    arguments_template: str = "{}"  # Jinja2-style template
    output_key: str = ""  # Key to store result in context
    condition: str = ""  # Expression or 'else'
    is_else: bool = False  # True if step executes on prior condition false
    else_skill_name: str = ""  # Alternative skill if condition evaluates to False
    else_tool_name: str = ""  # Alternative tool if condition evaluates to False
    else_arguments_template: str = "{}"
    else_output_key: str = ""


@dataclass(slots=True)
class SkillManifest:
    """Manifest describing a reusable skill."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    steps: List[SkillStep] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    signature: str = ""  # Base64-encoded Ed25519 signature
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    depends: List[str] = field(default_factory=list)
    user_invocable: bool = True
    disable_model_invocation: bool = False
    markdown_content: str = ""  # loaded from SKILL.md

    def manifest_bytes(self) -> bytes:
        """Serialize the manifest (excluding signature) for signing/verification."""
        import json

        data = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "steps": [
                {
                    "tool_name": s.tool_name,
                    "skill_name": s.skill_name,
                    "arguments_template": s.arguments_template,
                    "output_key": s.output_key,
                    "condition": s.condition,
                    "is_else": s.is_else,
                    "else_skill_name": s.else_skill_name,
                    "else_tool_name": s.else_tool_name,
                    "else_arguments_template": s.else_arguments_template,
                    "else_output_key": s.else_output_key,
                }
                for s in self.steps
            ],
            "required_capabilities": self.required_capabilities,
            "tags": self.tags,
            "depends": self.depends,
        }
        return json.dumps(data, sort_keys=True).encode()


__all__ = ["SkillManifest", "SkillStep"]
