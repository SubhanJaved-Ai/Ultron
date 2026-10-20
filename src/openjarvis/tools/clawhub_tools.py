"""ClawHub On-Demand Community Skill Discovery and Auto-Loading Tools.

Provides autonomous subagents and users with access to OpenClaw's ecosystem
of ~13,700 community skills. Subagents can dynamically search, inspect,
and install skills at runtime to expand their capabilities on the fly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.skills.executor import SkillExecutor
from openjarvis.skills.importer import SkillImporter
from openjarvis.skills.loader import load_skill_directory
from openjarvis.skills.parser import SkillParser
from openjarvis.skills.sources.base import ResolvedSkill
from openjarvis.skills.sources.openclaw import OpenClawResolver
from openjarvis.skills.tool_adapter import SkillTool
from openjarvis.skills.tool_translator import ToolTranslator
from openjarvis.tools._stubs import BaseTool, ToolExecutor, ToolSpec

logger = logging.getLogger(__name__)

# Curated fallback/standard community catalog when git cache is not yet cloned
_CURATED_COMMUNITY_SKILLS: List[Dict[str, str]] = [
    {
        "name": "web-scraper",
        "category": "openclaw",
        "description": "Extract clean markdown and semantic data from web pages.",
        "prompt": (
            "You are a web extraction expert. Given a URL or HTML, "
            "extract semantic headings, tables, and clean text."
        ),
    },
    {
        "name": "figma-tokens",
        "category": "design",
        "description": "Parse design tokens and typography from Figma styles.",
        "prompt": (
            "You are a design system engineer. Translate design tokens into "
            "CSS variables and JSON schemas."
        ),
    },
    {
        "name": "slack-notify",
        "category": "integrations",
        "description": "Format and dispatch alerts and messages to Slack.",
        "prompt": (
            "Format rich message attachments and Block Kit elements for "
            "team notifications."
        ),
    },
    {
        "name": "docker-compose",
        "category": "devops",
        "description": "Validate multi-service Docker Compose configurations.",
        "prompt": (
            "Design production-ready compose manifests with health checks, "
            "volumes, and networks."
        ),
    },
    {
        "name": "postgres-query",
        "category": "database",
        "description": "Analyze query performance and introspect PostgreSQL schemas.",
        "prompt": (
            "You are a DBA specialist. Analyze query plans, index suggestions, "
            "and table structures."
        ),
    },
    {
        "name": "arxiv-search",
        "category": "research",
        "description": "Search literature and synthesize papers from arXiv.",
        "prompt": "Query academic repositories and synthesize findings with citations.",
    },
    {
        "name": "github-explorer",
        "category": "devtools",
        "description": "Search GitHub repositories, compare branches, and inspect PRs.",
        "prompt": "Explore repository trees, git logs, and pull request activity.",
    },
    {
        "name": "pdf-processor",
        "category": "document",
        "description": "Extract text, tables, and metadata from structured PDFs.",
        "prompt": "Parse complex PDF layouts into structured JSON and markdown.",
    },
]


def _get_installed_skill_names() -> set[str]:
    """Return set of installed skill names from ~/.openjarvis/skills."""
    skills_root = get_config_dir() / "skills"
    installed = set()
    if not skills_root.exists():
        return installed

    for p in skills_root.rglob("*"):
        if p.is_dir() and ((p / "SKILL.md").exists() or (p / "skill.toml").exists()):
            installed.add(p.name)
    return installed


def _resolve_all_clawhub_skills(
    resolver: Optional[OpenClawResolver] = None,
) -> List[ResolvedSkill]:
    """Gather all discoverable skills from OpenClawResolver and curated catalog."""
    res = resolver or OpenClawResolver()
    skills_map: Dict[str, ResolvedSkill] = {}

    # 1. Read live skills from cache directory if available
    try:
        for s in res.list_skills():
            skills_map[s.name] = s
    except Exception as exc:
        logger.debug("Failed to list skills from OpenClawResolver: %s", exc)

    # 2. Add curated catalog skills if not already present in live cache
    cache_root = res.cache_dir()
    for item in _CURATED_COMMUNITY_SKILLS:
        name = item["name"]
        if name not in skills_map:
            virtual_path = cache_root / "skills" / item["category"] / name
            skills_map[name] = ResolvedSkill(
                name=name,
                source="openclaw",
                path=virtual_path,
                category=item["category"],
                description=item["description"],
                commit="curated-v1",
                sidecar_data={"prompt": item["prompt"]},
            )

    return list(skills_map.values())


# ---------------------------------------------------------------------------
# ClawHubSearchTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("clawhub_search")
class ClawHubSearchTool(BaseTool):
    """Search OpenClaw / ClawHub community skills catalog."""

    tool_id = "clawhub_search"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="clawhub_search",
            description=(
                "Search the ClawHub / OpenClaw community skill index "
                "(~13,700 skills) by keyword, capability, or category. "
                "Returns matching skill names and descriptions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Keyword or substring to search for "
                            "(e.g. 'scraper', 'postgres', 'docker')."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category or author filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 15).",
                        "default": 15,
                    },
                },
            },
            category="skills",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        query = str(params.get("query") or "").lower().strip()
        category_filter = str(params.get("category") or "").lower().strip()
        limit = int(params.get("limit") or 15)

        all_skills = _resolve_all_clawhub_skills()
        installed_names = _get_installed_skill_names()

        matches = []
        for s in all_skills:
            if category_filter and category_filter not in s.category.lower():
                continue
            if query:
                in_name = query in s.name.lower()
                in_desc = query in s.description.lower()
                in_cat = query in s.category.lower()
                if not (in_name or in_desc or in_cat):
                    continue
            matches.append(
                {
                    "name": s.name,
                    "category": s.category,
                    "description": s.description,
                    "installed": s.name in installed_names,
                }
            )
            if len(matches) >= limit:
                break

        return ToolResult(
            tool_name="clawhub_search",
            content=json.dumps(
                {
                    "query": query,
                    "total_matches": len(matches),
                    "skills": matches,
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# ClawHubInfoTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("clawhub_info")
class ClawHubInfoTool(BaseTool):
    """Inspect detailed information about a ClawHub skill."""

    tool_id = "clawhub_info"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="clawhub_info",
            description=(
                "Inspect details, instructions, description, and required parameters "
                "for a specific ClawHub community skill before installing or using it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": (
                            "Name of skill to inspect (e.g. 'web-scraper')."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category or author filter.",
                    },
                },
                "required": ["skill_name"],
            },
            category="skills",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        skill_name = str(params.get("skill_name", "")).strip().lower()
        if not skill_name:
            return ToolResult(
                tool_name="clawhub_info",
                content="Parameter 'skill_name' is required.",
                success=False,
            )

        category = str(params.get("category", "")).strip().lower()
        all_skills = _resolve_all_clawhub_skills()

        target = None
        for s in all_skills:
            if s.name.lower() == skill_name:
                if not category or category == s.category.lower():
                    target = s
                    break

        if not target:
            return ToolResult(
                tool_name="clawhub_info",
                content=f"Skill '{skill_name}' not found in ClawHub index.",
                success=False,
            )

        installed_names = _get_installed_skill_names()
        is_installed = target.name in installed_names

        content_body = ""
        skill_md = target.path / "SKILL.md"
        if skill_md.exists():
            try:
                content_body = skill_md.read_text(encoding="utf-8")
            except Exception:
                pass

        if not content_body and target.sidecar_data.get("prompt"):
            content_body = target.sidecar_data["prompt"]

        info = {
            "name": target.name,
            "category": target.category,
            "source": target.source,
            "description": target.description,
            "installed": is_installed,
            "commit": target.commit,
            "instructions_preview": content_body[:1000],
        }

        return ToolResult(
            tool_name="clawhub_info",
            content=json.dumps(info),
            success=True,
        )


# ---------------------------------------------------------------------------
# ClawHubInstallTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("clawhub_install")
class ClawHubInstallTool(BaseTool):
    """Download, install, and auto-load a ClawHub skill into Jarvis."""

    tool_id = "clawhub_install"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="clawhub_install",
            description=(
                "Install a community skill from ClawHub / OpenClaw into Jarvis 2.0. "
                "The newly installed skill is immediately compiled and registered into "
                "ToolRegistry as an executable tool for both the parent agent and "
                "any subagents."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the ClawHub skill to install.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional author/category filter.",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "If true, overwrite existing installed skill.",
                        "default": False,
                    },
                    "with_scripts": {
                        "type": "boolean",
                        "description": "Allow importing executable helper scripts.",
                        "default": False,
                    },
                    "subagent_id": {
                        "type": "string",
                        "description": (
                            "Optional calling subagent ID to grant the new tool."
                        ),
                    },
                },
                "required": ["skill_name"],
            },
            category="skills",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        skill_name = str(params.get("skill_name", "")).strip().lower()
        if not skill_name:
            return ToolResult(
                tool_name="clawhub_install",
                content="Parameter 'skill_name' is required.",
                success=False,
            )

        category = str(params.get("category", "")).strip().lower()
        force = bool(params.get("force", False))
        with_scripts = bool(params.get("with_scripts", False))
        subagent_id = params.get("subagent_id")

        all_skills = _resolve_all_clawhub_skills()
        target = None
        for s in all_skills:
            if s.name.lower() == skill_name:
                if not category or category == s.category.lower():
                    target = s
                    break

        if not target:
            return ToolResult(
                tool_name="clawhub_install",
                content=f"Skill '{skill_name}' not found in ClawHub index.",
                success=False,
            )

        # If target has a virtual path (from curated catalog) without an on-disk
        # SKILL.md, materialize it
        if not (target.path / "SKILL.md").exists():
            target.path.mkdir(parents=True, exist_ok=True)
            prompt = target.sidecar_data.get("prompt", target.description)
            sample_content = (
                f"---\nname: {target.name}\ndescription: {target.description}\n---\n\n"
                f"# {target.name}\n\n{prompt}\n"
            )
            (target.path / "SKILL.md").write_text(sample_content, encoding="utf-8")

        # Run SkillImporter
        importer = SkillImporter(parser=SkillParser(), tool_translator=ToolTranslator())
        result = importer.import_skill(
            target,
            with_scripts=with_scripts,
            force=force,
            confirm_dangerous=True,
        )

        if not result.success:
            err_msg = "; ".join(result.warnings or ["Unknown error"])
            return ToolResult(
                tool_name="clawhub_install",
                content=f"Install failed: {err_msg}",
                success=False,
            )

        # Hot-load manifest into ToolRegistry as an executable SkillTool
        registered_tool_name = target.name
        if result.target_path and result.target_path.exists():
            try:
                manifest = load_skill_directory(result.target_path)
                if manifest is not None:
                    skill_tool = SkillTool(
                        manifest, SkillExecutor(ToolExecutor(tools=[]))
                    )
                    # Register into ToolRegistry
                    if not ToolRegistry.contains(manifest.name):
                        ToolRegistry.register_value(
                            manifest.name, lambda t=skill_tool: t
                        )
                    else:
                        ToolRegistry._entries()[manifest.name] = lambda t=skill_tool: t
                    registered_tool_name = manifest.name
            except Exception as exc:
                logger.warning(
                    "Failed to auto-register SkillTool for %s: %s", target.name, exc
                )

        # If invoked by a subagent, grant access to the newly registered tool
        if subagent_id:
            try:
                from openjarvis.agents.subagents import get_subagent_manager

                mgr = get_subagent_manager()
                sub = mgr.get(subagent_id)
                if sub and registered_tool_name not in sub.tools:
                    sub.tools.append(registered_tool_name)
            except Exception:
                pass

        return ToolResult(
            tool_name="clawhub_install",
            content=json.dumps(
                {
                    "skill_name": target.name,
                    "target_path": str(result.target_path),
                    "status": "installed",
                    "registered_tool": registered_tool_name,
                    "skipped": result.skipped,
                    "translated_tools": result.translated_tools,
                    "warnings": result.warnings,
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# ClawHubListInstalledTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("clawhub_list_installed")
class ClawHubListInstalledTool(BaseTool):
    """List all installed ClawHub / community skills in Jarvis."""

    tool_id = "clawhub_list_installed"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="clawhub_list_installed",
            description="List all installed ClawHub skills available in Jarvis 2.0.",
            parameters={"type": "object", "properties": {}},
            category="skills",
            required_capabilities=[],
        )

    def execute(self, **params: Any) -> ToolResult:
        installed_names = sorted(_get_installed_skill_names())
        return ToolResult(
            tool_name="clawhub_list_installed",
            content=json.dumps(
                {
                    "count": len(installed_names),
                    "installed_skills": installed_names,
                }
            ),
            success=True,
        )


__all__ = [
    "ClawHubInfoTool",
    "ClawHubInstallTool",
    "ClawHubListInstalledTool",
    "ClawHubSearchTool",
]
