"""Ultron Workflow Skill Learner.

Converts verified, repeatable task workflows into reusable SkillManifests.
Features structural fingerprinting to prevent duplicates, tamper protection
for trusted/system skills, ledger audit trails, and health validation to
detect outdated skills.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import ToolRegistry
from openjarvis.security.capabilities import (
    DEFAULT_TOOL_CAPABILITIES,
    Capability,
    CapabilityPolicy,
)
from openjarvis.skills.ledger import SkillLedger
from openjarvis.skills.manager import SkillManager
from openjarvis.skills.types import SkillManifest, SkillStep
from openjarvis.tasks.types import StepStatus, TaskRecord, TaskStatus, TaskStep

logger = logging.getLogger(__name__)

# Protected tags indicating a skill must never be overwritten by automated task learning
PROTECTED_SKILL_TAGS = frozenset({"builtin", "system", "trusted", "core"})
PROTECTED_AUTHORS = frozenset({"system", "openjarvis", "openjarvis (built-in)"})


class SkillApprovalStatus:
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkflowSkillLearner:
    """Learns, validates, and maintains reusable skills derived from verified task workflows."""

    def __init__(
        self,
        skill_manager: Optional[SkillManager] = None,
        skills_dir: Optional[Path] = None,
        ledger: Optional[SkillLedger] = None,
    ) -> None:
        self.skill_manager = skill_manager
        self.skills_dir = (
            Path(skills_dir).expanduser()
            if skills_dir
            else get_config_dir() / "skills"
        )
        self.ledger = ledger or SkillLedger(skills_dir=self.skills_dir)

    # ------------------------------------------------------------------
    # 1. Structural Fingerprinting (Duplicate Prevention)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_workflow_fingerprint(steps: List[TaskStep | SkillStep | Dict[str, Any]]) -> str:
        """Compute a canonical structural fingerprint for a sequence of workflow steps.

        Considers tool names, dependency structure, and argument key sets.
        Ignores concrete argument values to recognize equivalent workflows.
        """
        # Build relative index mapping for step IDs to decouple from arbitrary random IDs
        step_id_to_idx: Dict[str, int] = {}
        for idx, s in enumerate(steps):
            if isinstance(s, TaskStep) and s.step_id:
                step_id_to_idx[s.step_id] = idx
            elif isinstance(s, dict) and s.get("step_id"):
                step_id_to_idx[str(s["step_id"])] = idx

        canonical_items = []
        for s in steps:
            if isinstance(s, TaskStep):
                t_name = s.tool_name.strip().lower()
                norm_deps = sorted(step_id_to_idx.get(str(d), str(d)) for d in s.dependencies)
                arg_keys = sorted((s.tool_args or {}).keys())
            elif isinstance(s, SkillStep):
                t_name = (s.tool_name or s.skill_name).strip().lower()
                norm_deps = []
                # parse template keys if JSON
                try:
                    tpl_dict = json.loads(s.arguments_template)
                    arg_keys = sorted(tpl_dict.keys()) if isinstance(tpl_dict, dict) else []
                except Exception:
                    arg_keys = []
            elif isinstance(s, dict):
                t_name = str(s.get("tool_name") or s.get("tool") or "").strip().lower()
                norm_deps = sorted(step_id_to_idx.get(str(d), str(d)) for d in s.get("dependencies", []))
                arg_keys = sorted(dict(s.get("tool_args", {})).keys())
            else:
                continue

            # Skip pure cognitive thoughts from structural fingerprinting
            if t_name == "think":
                continue

            canonical_items.append({
                "tool": t_name,
                "dependencies": norm_deps,
                "arg_keys": arg_keys,
            })

        blob = json.dumps(canonical_items, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # 2. Skill Learning from Task
    # ------------------------------------------------------------------

    def learn_skill_from_task(
        self,
        task: TaskRecord,
        skill_name: Optional[str] = None,
        description: Optional[str] = None,
        min_steps: int = 2,
    ) -> Optional[SkillManifest]:
        """Convert a verified successful task execution into a reusable skill.

        Requirements:
        - Task must be COMPLETED.
        - Every step must be COMPLETED and verified.
        - Prevents duplicates via structural fingerprinting.
        - Refuses to overwrite trusted/system skills.
        - Logs audit trail in SkillLedger.
        """
        # 1. Honest Verification Gate
        if task.status != TaskStatus.COMPLETED:
            logger.info("Task %s is not COMPLETED; refusing to learn skill.", task.task_id)
            return None

        # Verify all steps actually completed
        for s in task.steps:
            if s.status != StepStatus.COMPLETED:
                logger.info(
                    "Task %s has uncompleted step %s (%s); refusing to learn skill.",
                    task.task_id,
                    s.step_id,
                    s.status.value,
                )
                return None

        # Filter out think steps for operational skill pipeline
        operational_steps = [s for s in task.steps if s.tool_name.lower() != "think"]
        if len(operational_steps) < min_steps:
            logger.debug(
                "Task %s has only %d operational steps (min=%d); skipping skill creation.",
                task.task_id,
                len(operational_steps),
                min_steps,
            )
            return None

        # 2. Compute Structural Fingerprint
        fingerprint = self.compute_workflow_fingerprint(operational_steps)

        # 3. Check for Existing Duplicate Skills
        if self.skill_manager is not None:
            for existing_name in self.skill_manager.skill_names():
                try:
                    existing_manifest = self.skill_manager.resolve(existing_name)
                    existing_fp = (existing_manifest.metadata or {}).get("structural_fingerprint")
                    if existing_fp == fingerprint:
                        logger.info(
                            "Workflow matching task %s already exists as skill '%s'. Incrementing usage count.",
                            task.task_id,
                            existing_name,
                        )
                        count = (existing_manifest.metadata or {}).get("execution_count", 1)
                        existing_manifest.metadata["execution_count"] = count + 1
                        existing_manifest.metadata["last_used_at"] = time.time()
                        return existing_manifest
                except KeyError:
                    pass

        # 4. Generate Kebab Skill Name
        if not skill_name:
            # Generate from prompt
            clean_prompt = re.sub(r"[^a-zA-Z0-9\s]", "", task.prompt).strip().lower()
            tokens = [t for t in clean_prompt.split() if t not in ("a", "an", "the", "to", "for", "in", "of")][:4]
            base_name = "-".join(tokens) or f"task-workflow-{task.task_id[:8]}"
            skill_name = f"learned-{base_name}"

        skill_name = re.sub(r"[^a-z0-9_-]", "-", skill_name.lower()).strip("-")

        # 5. Tamper & Security Protection: Guard Trusted / System Skills
        if self.skill_manager is not None:
            try:
                target_manifest = self.skill_manager.resolve(skill_name)
                # Check tags and author
                is_protected_author = target_manifest.author.lower() in PROTECTED_AUTHORS
                is_protected_tag = bool(set(target_manifest.tags or ()) & PROTECTED_SKILL_TAGS)
                if is_protected_author or is_protected_tag:
                    raise PermissionError(
                        f"Security Violation: Learned task workflow attempted to overwrite "
                        f"protected skill '{skill_name}' (author: {target_manifest.author}, tags: {target_manifest.tags})."
                    )
            except KeyError:
                pass  # Skill does not exist yet; safe to create

        # 6. Extract Inputs, Dependencies, and Steps
        skill_steps: List[SkillStep] = []
        required_caps: Set[str] = set()

        for s in operational_steps:
            t_clean = s.tool_name.strip().lower()
            caps = DEFAULT_TOOL_CAPABILITIES.get(t_clean)
            if caps:
                for c in caps:
                    required_caps.add(c.value if hasattr(c, "value") else str(c))
            else:
                required_caps.add(Capability.TOOL_INVOKE.value)

            # Map arguments into template form
            # Parameterize variable args or keep explicit references
            tpl_args: Dict[str, Any] = {}
            for k, v in (s.tool_args or {}).items():
                if isinstance(v, str) and ("{{" in v or "$" in v):
                    tpl_args[k] = v
                else:
                    tpl_args[k] = v

            tpl_str = json.dumps(tpl_args)
            output_key = f"{s.step_id}_output"

            skill_steps.append(
                SkillStep(
                    tool_name=s.tool_name,
                    arguments_template=tpl_str,
                    output_key=output_key,
                )
            )

        manifest = SkillManifest(
            name=skill_name,
            version="0.1.0",
            description=(description or f"Learned skill from verified task: {task.prompt}")[:1024],
            author="openjarvis (experience-learning)",
            steps=skill_steps,
            required_capabilities=sorted(list(required_caps)),
            tags=["learned", "verified-workflow", SkillApprovalStatus.PENDING_REVIEW],
            metadata={
                "task_id": task.task_id,
                "prompt": task.prompt,
                "learned_at": time.time(),
                "structural_fingerprint": fingerprint,
                "execution_count": 1,
                "verified": True,
                "approval_status": SkillApprovalStatus.PENDING_REVIEW,
                "approved": False,
            },
            user_invocable=False,  # Unapproved: cannot be invoked directly
            disable_model_invocation=True,  # Unapproved: hidden from LLM catalog
        )

        # 7. Persist and Audit via SkillLedger
        self.save_and_register_skill(manifest)
        return manifest

    def save_and_register_skill(
        self,
        manifest: SkillManifest,
        overwrite: bool = True,
        action: Optional[str] = None,
    ) -> Path:
        """Persist a skill manifest to disk, audit in ledger, and register in SkillManager."""
        skill_dir = self.skills_dir / manifest.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        toml_path = skill_dir / "skill.toml"

        is_update = toml_path.exists()
        before_manifest_dict: Dict[str, str] = {}
        if is_update:
            before_manifest_dict = self.ledger.capture_snapshot(skill_dir)

        # Serialize manifest
        toml_content = self._serialize_manifest_toml(manifest)
        toml_path.write_text(toml_content, encoding="utf-8")

        after_manifest_dict = self.ledger.capture_snapshot(skill_dir)

        # Record in SkillLedger with granular action
        meta = manifest.metadata or {}
        if action is None:
            if meta.get("disabled") is True:
                action = "disable"
            elif meta.get("approved") is True and meta.get("approval_status") == SkillApprovalStatus.APPROVED:
                action = "approve"
            elif meta.get("approval_status") == SkillApprovalStatus.REJECTED:
                action = "reject"
            else:
                action = "patch" if is_update else "create"

        self.ledger.record_mutation(
            skill_name=manifest.name,
            action=action,
            author=manifest.author,
            description=f"{action.capitalize()} skill '{manifest.name}' ({meta.get('approval_status', 'created')}).",
            before_manifest=before_manifest_dict,
            after_manifest=after_manifest_dict,
        )

        # Register in SkillManager if present
        if self.skill_manager is not None:
            if hasattr(self.skill_manager, "_skills"):
                self.skill_manager._skills[manifest.name] = manifest

        logger.info(
            "Successfully saved and registered skill '%s' (%s) at %s",
            manifest.name,
            meta.get("approval_status", "unknown"),
            toml_path,
        )
        return toml_path

    # ------------------------------------------------------------------
    # 3. Approval Lifecycle & Security Gating
    # ------------------------------------------------------------------

    def is_skill_approved(self, manifest: SkillManifest) -> bool:
        """Return True if the skill is approved for discovery and execution.

        Core / system / trusted skills are approved by default.
        Learned skills must have explicit approved=True and approval_status='approved'.
        Disabled skills always return False.
        """
        # Disabled skills are not approved for execution or discovery
        meta = manifest.metadata or {}
        if meta.get("disabled") is True:
            return False

        # Explicit pending review, draft, or rejected skills are never approved
        if meta.get("approval_status") in (
            SkillApprovalStatus.PENDING_REVIEW,
            SkillApprovalStatus.DRAFT,
            SkillApprovalStatus.REJECTED,
        ):
            return False
        if meta.get("approved") is False:
            return False

        # 1. System/core skills are approved by default
        if (manifest.author or "").lower() in PROTECTED_AUTHORS:
            return True
        if bool(set(manifest.tags or ()) & PROTECTED_SKILL_TAGS):
            return True

        # 2. Check metadata approval status
        if meta.get("approved") is True and meta.get("approval_status") == SkillApprovalStatus.APPROVED:
            return True

        # 3. Check tags
        if "approved" in (manifest.tags or []) and "pending_review" not in (manifest.tags or []):
            return True

        return False

    def validate_skill_for_approval(
        self,
        manifest: SkillManifest,
        registered_tools: Optional[List[str]] = None,
    ) -> Tuple[bool, List[str]]:
        """Validate tool mappings, argument schemas, dependencies, and required capabilities.

        Returns (is_valid, list_of_validation_errors).
        """
        errors: List[str] = []

        # 1. Guard protected core/system skills
        if manifest.author.lower() in PROTECTED_AUTHORS or bool(set(manifest.tags or ()) & PROTECTED_SKILL_TAGS):
            errors.append(f"Cannot approve or mutate protected core/system skill '{manifest.name}'.")

        if not manifest.steps:
            errors.append("Skill must have at least one execution step.")

        # 2. Check tool mappings
        # Check against ToolRegistry and built-ins
        known_tools = set(ToolRegistry.keys()) | {
            "think", "delete_file", "file_delete", "remove_file", "app_launch", "launch_app",
            "file_write", "file_read", "shell_exec", "http_request", "web_search", "calculator",
            "create_file", "write_file", "read_file", "cmd_exec", "bash", "powershell", "fetch_url"
        }
        if registered_tools:
            known_tools |= {t.lower() for t in registered_tools}

        if self.skill_manager is not None:
            for s_name in self.skill_manager.skill_names():
                if s_name != manifest.name:
                    try:
                        other_manifest = self.skill_manager.resolve(s_name)
                        if self.is_skill_approved(other_manifest):
                            known_tools.add(s_name.lower())
                    except Exception:
                        pass

        output_keys_produced: Set[str] = set()

        for idx, step in enumerate(manifest.steps):
            step_tool = (step.tool_name or step.skill_name or "").strip().lower()
            if not step_tool:
                errors.append(f"Step {idx+1} has no tool_name or skill_name specified.")
                continue

            if step_tool not in known_tools:
                errors.append(f"Step {idx+1} references unknown or unregistered tool '{step_tool}'.")

            # Validate arguments template JSON syntax
            if step.arguments_template:
                try:
                    args_obj = json.loads(step.arguments_template)
                    if not isinstance(args_obj, dict):
                        errors.append(f"Step {idx+1} arguments_template must be a JSON object, got {type(args_obj).__name__}.")
                    else:
                        # Check dependency outputs: e.g. {{output_key}}
                        for val in args_obj.values():
                            if isinstance(val, str) and "{{" in val:
                                placeholders = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", val)
                                for ph in placeholders:
                                    if ph not in output_keys_produced and ph not in ("input", "args", "kwargs"):
                                        errors.append(
                                            f"Step {idx+1} references output key '{ph}' before it is produced by any prior step."
                                        )
                except json.JSONDecodeError as exc:
                    errors.append(f"Step {idx+1} arguments_template contains invalid JSON: {exc}")

            if step.output_key:
                output_keys_produced.add(step.output_key)

        # 3. Check composition rules if steps invoke child skills
        if any(s.skill_name for s in manifest.steps) and self.skill_manager is not None:
            from openjarvis.skills.composition import (
                CompositionValidationError,
                compute_composite_capabilities,
                validate_composite_skill,
            )

            try:
                validate_composite_skill(manifest, self.skill_manager)
            except CompositionValidationError as cve:
                errors.append(f"Skill composition validation failed: {cve}")

        # 4. Check required capabilities coverage (including transitive child skills)
        declared_caps = set(manifest.required_capabilities or [])

        if any(s.skill_name for s in manifest.steps) and self.skill_manager is not None:
            from openjarvis.skills.composition import compute_composite_capabilities

            expected_caps = compute_composite_capabilities(manifest, self.skill_manager)
            missing_caps = [c for c in expected_caps if c not in declared_caps]
            if missing_caps:
                errors.append(
                    f"Composite skill is missing required transitive capabilities: {missing_caps}."
                )

        for step in manifest.steps:
            if not step.tool_name:
                continue
            step_tool = step.tool_name.strip().lower()
            canonical_tool = step_tool
            # Standard verb mappings
            verb_map = {
                "create_file": "file_write",
                "write_file": "file_write",
                "read_file": "file_read",
                "cmd_exec": "shell_exec",
                "bash": "shell_exec",
                "powershell": "shell_exec",
                "delete_file": "delete_file",
                "file_delete": "delete_file",
            }
            canonical_tool = verb_map.get(step_tool, step_tool)
            tool_caps = DEFAULT_TOOL_CAPABILITIES.get(canonical_tool)
            if tool_caps:
                for c in tool_caps:
                    c_val = c.value if hasattr(c, "value") else str(c)
                    if c_val not in declared_caps:
                        errors.append(
                            f"Skill requires capability '{c_val}' for step tool '{step_tool}', "
                            "but it is missing from required_capabilities."
                        )

        return len(errors) == 0, errors


    def approve_skill(
        self,
        skill_name: str,
        approver_id: str = "admin",
        capability_policy: Optional[CapabilityPolicy] = None,
        registered_tools: Optional[List[str]] = None,
    ) -> SkillManifest:
        """Explicitly approve a draft/pending_review learned skill.

        Validates tool mappings, argument schemas, dependencies, and required capabilities.
        Enforces that approval does NOT bypass security or grant new capabilities.
        """
        if self.skill_manager is None:
            raise RuntimeError("SkillManager is required to approve skills.")

        manifest = self.skill_manager.resolve(skill_name)

        # 1. Anti-tamper: Never modify protected core/system skills
        if manifest.author.lower() in PROTECTED_AUTHORS or bool(set(manifest.tags or ()) & PROTECTED_SKILL_TAGS):
            raise PermissionError(
                f"Security Violation: Cannot modify or approve protected core/system skill '{skill_name}'."
            )

        # 2. Check approver authorization if CapabilityPolicy is provided
        if capability_policy is not None:
            # Approver must have permission to manage skills (system:admin)
            if not capability_policy.check(approver_id, Capability.SYSTEM_ADMIN.value, "skill_approval"):
                raise PermissionError(
                    f"Approver '{approver_id}' lacks capability '{Capability.SYSTEM_ADMIN.value}' to approve skills."
                )

        # 3. Comprehensive Validation
        is_valid, validation_errors = self.validate_skill_for_approval(manifest, registered_tools=registered_tools)
        if not is_valid:
            error_details = "; ".join(validation_errors)
            raise ValueError(f"Skill validation failed for '{skill_name}': {error_details}")

        # 4. Update manifest state to APPROVED
        metadata = dict(manifest.metadata or {})
        metadata["approved"] = True
        metadata["approval_status"] = SkillApprovalStatus.APPROVED
        metadata["approved_by"] = approver_id
        metadata["approved_at"] = time.time()
        metadata.pop("rejection_reason", None)

        manifest.metadata = metadata
        manifest.user_invocable = True
        manifest.disable_model_invocation = False

        # Update tags
        tags = [t for t in (manifest.tags or []) if t not in (SkillApprovalStatus.PENDING_REVIEW, SkillApprovalStatus.DRAFT, SkillApprovalStatus.REJECTED)]
        if SkillApprovalStatus.APPROVED not in tags:
            tags.append(SkillApprovalStatus.APPROVED)
        manifest.tags = tags

        # 5. Persist to disk and record in SkillLedger
        self.save_and_register_skill(manifest, overwrite=True)
        return manifest

    def reject_skill(
        self,
        skill_name: str,
        reviewer_id: str = "admin",
        reason: str = "",
    ) -> SkillManifest:
        """Reject a draft or pending_review learned skill."""
        if self.skill_manager is None:
            raise RuntimeError("SkillManager is required to reject skills.")

        manifest = self.skill_manager.resolve(skill_name)
        if manifest.author.lower() in PROTECTED_AUTHORS or bool(set(manifest.tags or ()) & PROTECTED_SKILL_TAGS):
            raise PermissionError(
                f"Security Violation: Cannot reject or modify protected core/system skill '{skill_name}'."
            )

        metadata = dict(manifest.metadata or {})
        metadata["approved"] = False
        metadata["approval_status"] = SkillApprovalStatus.REJECTED
        metadata["rejection_reason"] = reason or "Rejected during security review."
        metadata["reviewed_by"] = reviewer_id
        metadata["reviewed_at"] = time.time()

        manifest.metadata = metadata
        manifest.user_invocable = False
        manifest.disable_model_invocation = True

        tags = [t for t in (manifest.tags or []) if t != SkillApprovalStatus.PENDING_REVIEW]
        if SkillApprovalStatus.REJECTED not in tags:
            tags.append(SkillApprovalStatus.REJECTED)
        manifest.tags = tags

        self.save_and_register_skill(manifest, overwrite=True)
        return manifest

    def disable_skill(
        self,
        skill_name: str,
        operator_id: str = "admin",
        reason: str = "",
    ) -> SkillManifest:
        """Disable an approved or active learned skill."""
        if self.skill_manager is None:
            raise RuntimeError("SkillManager is required to disable skills.")

        manifest = self.skill_manager.resolve(skill_name)
        if manifest.author.lower() in PROTECTED_AUTHORS or bool(set(manifest.tags or ()) & PROTECTED_SKILL_TAGS):
            raise PermissionError(
                f"Security Violation: Cannot disable or modify protected core/system skill '{skill_name}'."
            )

        metadata = dict(manifest.metadata or {})
        metadata["disabled"] = True
        metadata["disabled_reason"] = reason or "Disabled by operator."
        metadata["disabled_by"] = operator_id
        metadata["disabled_at"] = time.time()

        manifest.metadata = metadata
        manifest.user_invocable = False
        manifest.disable_model_invocation = True

        self.save_and_register_skill(manifest, overwrite=True, action="disable")
        return manifest

    def enable_skill(
        self,
        skill_name: str,
        operator_id: str = "admin",
    ) -> SkillManifest:
        """Re-enable a previously disabled learned skill."""
        if self.skill_manager is None:
            raise RuntimeError("SkillManager is required to enable skills.")

        manifest = self.skill_manager.resolve(skill_name)
        if manifest.author.lower() in PROTECTED_AUTHORS or bool(set(manifest.tags or ()) & PROTECTED_SKILL_TAGS):
            raise PermissionError(
                f"Security Violation: Cannot modify protected core/system skill '{skill_name}'."
            )

        metadata = dict(manifest.metadata or {})
        if not (metadata.get("approved") is True and metadata.get("approval_status") == SkillApprovalStatus.APPROVED):
            raise ValueError(f"Cannot enable skill '{skill_name}': Skill is not approved. It must be approved first.")

        metadata["disabled"] = False
        metadata.pop("disabled_reason", None)
        metadata["enabled_by"] = operator_id
        metadata["enabled_at"] = time.time()

        manifest.metadata = metadata
        manifest.user_invocable = True
        manifest.disable_model_invocation = False

        self.save_and_register_skill(manifest, overwrite=True, action="enable")
        return manifest

    def list_skills(self) -> List[SkillManifest]:
        """List all registered and discovered skills from manager and storage."""
        results: Dict[str, SkillManifest] = {}
        if self.skill_manager is not None:
            for s_name in self.skill_manager.skill_names():
                try:
                    results[s_name] = self.skill_manager.resolve(s_name)
                except Exception:
                    pass

        # Also discover any on-disk skills from skills_dir not yet in skill_manager
        if self.skills_dir.exists():
            from openjarvis.skills.loader import discover_skills
            try:
                disk_skills = discover_skills(self.skills_dir)
                for s in disk_skills:
                    if s.name not in results:
                        results[s.name] = s
                        if self.skill_manager is not None and hasattr(self.skill_manager, "_skills"):
                            self.skill_manager._skills[s.name] = s
            except Exception as exc:
                logger.debug("Failed to discover on-disk skills: %s", exc)

        return list(results.values())

    # ------------------------------------------------------------------
    # 3. Health Validation & Outdated Skill Detection
    # ------------------------------------------------------------------

    def validate_skill_health(
        self,
        manifest: SkillManifest,
        registered_tools: Optional[List[str]] = None,
    ) -> Tuple[bool, List[str]]:
        """Validate whether a learned skill is healthy or outdated.

        Checks:
        - Outdated flag in metadata.
        - Availability of all required tools.
        - Consecutive failures threshold.

        Returns (is_healthy, list_of_issues).
        """
        issues: List[str] = []

        # Check explicit outdated flag
        if manifest.metadata and manifest.metadata.get("outdated"):
            reason = manifest.metadata.get("outdated_reason", "Marked outdated")
            issues.append(f"Skill is marked outdated: {reason}")

        # Check failure count
        consecutive_failures = (manifest.metadata or {}).get("consecutive_failures", 0)
        if consecutive_failures >= 3:
            issues.append(
                f"Skill has failed {consecutive_failures} consecutive times; workflow may be obsolete."
            )

        # Check tool availability
        if registered_tools is not None:
            avail_set = {t.lower() for t in registered_tools}
            for step in manifest.steps:
                tool = step.tool_name.strip().lower()
                if tool and tool not in avail_set:
                    issues.append(f"Required tool '{step.tool_name}' is not currently registered.")

        # Check child skill availability and health for composite skills
        if self.skill_manager is not None:
            for step in manifest.steps:
                if step.skill_name:
                    try:
                        child = self.skill_manager.resolve(step.skill_name)
                        child_meta = child.metadata or {}
                        if child_meta.get("disabled") is True:
                            issues.append(f"Child skill '{step.skill_name}' is disabled.")
                        if child_meta.get("outdated") is True:
                            issues.append(
                                f"Child skill '{step.skill_name}' is outdated: {child_meta.get('outdated_reason', '')}"
                            )
                    except KeyError:
                        issues.append(
                            f"Required child skill '{step.skill_name}' is missing from registry."
                        )

        is_healthy = len(issues) == 0
        return is_healthy, issues

    def compose_skills(
        self,
        name: str,
        steps: List[SkillStep | Dict[str, Any]],
        *,
        description: str = "",
        author: str = "operator",
        require_approval: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> SkillManifest:
        """Create and register a composite skill combining multiple approved child skills."""
        from openjarvis.skills.composition import create_composite_manifest

        manifest = create_composite_manifest(
            name=name,
            steps=steps,
            description=description,
            author=author,
            skill_manager=self.skill_manager,
            metadata=metadata,
            tags=tags,
            require_approval=require_approval,
        )

        self.save_and_register_skill(manifest, overwrite=True)
        return manifest


    def mark_skill_execution_result(
        self,
        skill_name: str,
        success: bool,
        error_reason: Optional[str] = None,
    ) -> None:
        """Update skill health metrics after execution. Outdates skills with repeated failures."""
        if self.skill_manager is None:
            return

        try:
            manifest = self.skill_manager.resolve(skill_name)
        except KeyError:
            return

        metadata = dict(manifest.metadata or {})
        if success:
            metadata["consecutive_failures"] = 0
            metadata["last_success_at"] = time.time()
            metadata["execution_count"] = metadata.get("execution_count", 0) + 1
        else:
            failures = metadata.get("consecutive_failures", 0) + 1
            metadata["consecutive_failures"] = failures
            metadata["last_failure_at"] = time.time()
            metadata["last_failure_reason"] = error_reason or "Unknown execution error"

            if failures >= 3:
                metadata["outdated"] = True
                metadata["outdated_reason"] = f"Failed {failures} consecutive times: {error_reason}"
                logger.warning(
                    "Skill '%s' has been marked OUTDATED after %d consecutive failures.",
                    skill_name,
                    failures,
                )

        manifest.metadata = metadata

    # ------------------------------------------------------------------
    # Serialization Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_manifest_toml(manifest: SkillManifest) -> str:
        """Serialize a SkillManifest to spec-compliant TOML format."""
        lines: List[str] = ["[skill]"]
        lines.append(f'name = "{manifest.name}"')
        lines.append(f'version = "{manifest.version}"')

        # Clean description
        desc = manifest.description.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'description = "{desc}"')
        lines.append(f'author = "{manifest.author}"')

        tags_str = ", ".join(f'"{t}"' for t in manifest.tags)
        lines.append(f"tags = [{tags_str}]")

        caps_str = ", ".join(f'"{c}"' for c in manifest.required_capabilities)
        lines.append(f"required_capabilities = [{caps_str}]")
        lines.append(f"user_invocable = {str(manifest.user_invocable).lower()}")
        lines.append(f"disable_model_invocation = {str(manifest.disable_model_invocation).lower()}")
        lines.append("")

        for step in manifest.steps:
            lines.append("[[skill.steps]]")
            if step.tool_name:
                lines.append(f'tool_name = "{step.tool_name}"')
            if step.skill_name:
                lines.append(f'skill_name = "{step.skill_name}"')

            # Arguments template
            arg_tpl = step.arguments_template.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'arguments_template = "{arg_tpl}"')
            lines.append(f'output_key = "{step.output_key}"')
            if getattr(step, "condition", ""):
                cond = step.condition.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'condition = "{cond}"')
            if getattr(step, "is_else", False):
                lines.append(f"is_else = {str(step.is_else).lower()}")
            if getattr(step, "else_skill_name", ""):
                lines.append(f'else_skill_name = "{step.else_skill_name}"')
            if getattr(step, "else_tool_name", ""):
                lines.append(f'else_tool_name = "{step.else_tool_name}"')
            if getattr(step, "else_arguments_template", "") and step.else_arguments_template != "{}":
                else_tpl = step.else_arguments_template.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'else_arguments_template = "{else_tpl}"')
            if getattr(step, "else_output_key", ""):
                lines.append(f'else_output_key = "{step.else_output_key}"')
            lines.append("")

        return "\n".join(lines)


__all__ = ["WorkflowSkillLearner", "SkillApprovalStatus", "PROTECTED_SKILL_TAGS", "PROTECTED_AUTHORS"]
