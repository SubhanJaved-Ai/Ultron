"""Ultron Safety Kernel — centralized 4-tier risk classification,
password-hashed safety code, plain-language custom rules engine,
and non-bypassable execution enforcement.
"""

from __future__ import annotations

import ctypes
import fnmatch
import hashlib
import json
import logging
import os
import re
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Four practical execution risk levels."""
    LOW = "low"            # Safe, authorized, executes automatically
    MEDIUM = "medium"      # Moderate impact, one-click user approval
    HIGH = "high"          # Destructive or external impact, explicit approval + safety code
    CRITICAL = "critical"  # Dangerous operations, hard-blocked by default (no code override)


class ActionEffect(str, Enum):
    """Kernel action authorization effects."""
    ALLOW = "allow"
    ASK = "ask"
    ASK_WITH_CODE = "ask_with_code"
    BLOCK = "block"


@dataclass
class SafetyDecision:
    """Evaluation result for an intercepted action."""
    effect: ActionEffect
    risk_level: RiskLevel
    reason: str
    action_type: str
    target: str
    fingerprint: str = ""
    preview: Optional[Dict[str, Any]] = None
    rule_id: Optional[str] = None
    requires_code: bool = False

    @property
    def is_allowed(self) -> bool:
        return self.effect == ActionEffect.ALLOW

    @property
    def is_blocked(self) -> bool:
        return self.effect == ActionEffect.BLOCK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect": self.effect.value,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "action_type": self.action_type,
            "target": self.target,
            "fingerprint": self.fingerprint,
            "preview": self.preview,
            "rule_id": self.rule_id,
            "requires_code": self.requires_code,
        }


# ---------------------------------------------------------------------------
# 1. Safety Code Manager (PBKDF2-HMAC-SHA256, salted, zero plain-text leaks)
# ---------------------------------------------------------------------------

class SafetyCodeManager:
    """Manages secure password-hashed safety codes and single-use action tokens."""

    PBKDF2_ITERATIONS = 120_000

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or (get_config_dir() / "safety_code.json")
        self._tokens: Dict[str, Dict[str, Any]] = {}  # token -> {fingerprint, expires_at, used}

    def is_code_set(self) -> bool:
        """Check if a safety code is configured."""
        if not self.storage_path.is_file():
            return False
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return bool(data.get("hash") and data.get("salt"))
        except Exception:
            return False

    def set_safety_code(self, new_code: str, old_code: Optional[str] = None) -> Tuple[bool, str]:
        """Set or update the safety code with PBKDF2-HMAC-SHA256 hashing."""
        clean = (new_code or "").strip()
        if len(clean) < 4:
            return False, "Safety code must be at least 4 characters long."

        if self.is_code_set():
            if not old_code:
                return False, "Existing safety code must be verified before changing."
            if not self.verify_safety_code(old_code):
                return False, "Incorrect current safety code."

        salt = secrets.token_bytes(16).hex()
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            clean.encode("utf-8"),
            bytes.fromhex(salt),
            self.PBKDF2_ITERATIONS,
        ).hex()

        payload = {
            "algorithm": "pbkdf2_sha256",
            "iterations": self.PBKDF2_ITERATIONS,
            "salt": salt,
            "hash": derived,
            "updated_at": time.time(),
        }

        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return True, "Safety code successfully configured."
        except Exception as exc:
            return False, f"Failed to save safety code: {exc}"

    def verify_safety_code(self, candidate_code: str) -> bool:
        """Verify candidate code using constant-time comparison."""
        if not self.is_code_set():
            return False
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            salt_hex = data.get("salt", "")
            stored_hash = data.get("hash", "")
            iterations = data.get("iterations", self.PBKDF2_ITERATIONS)

            candidate_derived = hashlib.pbkdf2_hmac(
                "sha256",
                candidate_code.strip().encode("utf-8"),
                bytes.fromhex(salt_hex),
                iterations,
            ).hex()

            return secrets.compare_digest(candidate_derived, stored_hash)
        except Exception:
            return False

    def compute_fingerprint(self, action_type: str, target: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Compute an immutable SHA256 fingerprint bound to exact action targets."""
        norm_target = str(Path(target).resolve(strict=False)) if target else ""
        norm_params = json.dumps(params or {}, sort_keys=True)
        raw = f"{action_type.lower()}|{norm_target.lower()}|{norm_params}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate_action_token(self, fingerprint: str, ttl_seconds: float = 300.0) -> str:
        """Generate a single-use authorization token bound to an action fingerprint."""
        token = f"sat_{secrets.token_hex(20)}"
        self._tokens[token] = {
            "fingerprint": fingerprint,
            "expires_at": time.time() + ttl_seconds,
            "used": False,
        }
        return token

    def consume_action_token(self, token: str, fingerprint: str) -> Tuple[bool, str]:
        """Verify and invalidate a single-use action token."""
        record = self._tokens.get(token)
        if not record:
            return False, "Invalid or unrecognized authorization token."

        if record["used"]:
            return False, "Authorization token has already been consumed."

        if time.time() > record["expires_at"]:
            self._tokens.pop(token, None)
            return False, "Authorization token has expired. Please re-authenticate."

        if not secrets.compare_digest(record["fingerprint"], fingerprint):
            return False, "Action fingerprint mismatch: the affected targets or parameters were modified."

        # Mark as consumed immediately (single-use)
        record["used"] = True
        return True, "Authorization confirmed."

    def is_token_valid(self, token: str, fingerprint: str) -> bool:
        """Check and consume a single-use action token."""
        ok, _ = self.consume_action_token(token, fingerprint)
        return ok

    # Convenience aliases
    set_code = set_safety_code
    verify_code = verify_safety_code
    issue_action_token = generate_action_token


# ---------------------------------------------------------------------------
# 2. Custom Safety Rules Engine (Plain-Language Compiler & Structured Evaluator)
# ---------------------------------------------------------------------------

@dataclass
class CustomRule:
    """A structured safety rule."""
    id: str
    raw_text: str
    effect: str                   # "ALLOW" | "DENY" | "ASK"
    action_types: List[str]       # ["read", "write", "delete", "execute", "*"]
    path_pattern: str             # e.g. "C:\\Windows\\*", "D:\\Projects\\*"
    risk_level: str = "medium"    # "low" | "medium" | "high" | "critical"
    created_at: float = field(default_factory=time.time)

    def matches(self, action_type: str, path: str) -> bool:
        """Check if action and path match this rule."""
        # 1. Action type match
        act = action_type.lower()
        if "*" not in self.action_types and not any(a in act for a in self.action_types):
            return False

        # 2. Path pattern match
        norm_p = str(Path(path).resolve(strict=False)).lower()
        pat = self.path_pattern.lower()

        # Handle drive wildcard matching (e.g. C:\* or C:*)
        if pat.endswith("*"):
            prefix = pat[:-1].rstrip("\\/")
            if norm_p.startswith(prefix.lower()):
                return True

        return fnmatch.fnmatch(norm_p, pat) or fnmatch.fnmatch(path.lower(), pat)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomRule:
        return cls(**data)


class CustomRuleEngine:
    """Compiles and evaluates plain-language safety rules."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or (get_config_dir() / "safety_rules.json")
        self._rules: List[CustomRule] = []
        self._load_rules()

    def _load_rules(self) -> None:
        if not self.storage_path.is_file():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._rules = [CustomRule.from_dict(r) for r in raw]
        except Exception as exc:
            logger.warning("Failed to load custom safety rules: %s", exc)

    def save_rules(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = [r.to_dict() for r in self._rules]
            self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save custom safety rules: %s", exc)

    def add_rule(self, rule: CustomRule) -> None:
        # Avoid duplicate rule IDs
        self._rules = [r for r in self._rules if r.id != rule.id]
        self._rules.append(rule)
        self.save_rules()

    def remove_rule(self, rule_id: str) -> bool:
        init_len = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        if len(self._rules) < init_len:
            self.save_rules()
            return True
        return False

    def list_rules(self) -> List[CustomRule]:
        return list(self._rules)

    @staticmethod
    def compile_plain_language(text: str) -> List[CustomRule]:
        """Convert a user's natural language instruction into structured rules.

        Handles phrases like:
        - "Ultron can read the C drive but cannot modify or delete files inside C:\\Windows."
        - "Ultron can create and edit files inside D:\\Projects."
        - "Ask my permission before deleting files elsewhere."
        """
        raw = text.strip()
        low = raw.lower()
        rules: List[CustomRule] = []

        # Pattern 1: Deny C:\Windows modifications
        if "c:\\windows" in low and any(w in low for w in ("cannot", "can't", "deny", "block", "prohibit")):
            rules.append(
                CustomRule(
                    id=f"rule_deny_windows_{secrets.token_hex(4)}",
                    raw_text=raw,
                    effect="DENY",
                    action_types=["write", "create", "modify", "delete", "edit"],
                    path_pattern="C:\\Windows\\*",
                    risk_level="critical",
                )
            )

        # Pattern 2: Allow read on C: drive
        if "read" in low and ("c drive" in low or "c:\\" in low):
            rules.append(
                CustomRule(
                    id=f"rule_allow_read_c_{secrets.token_hex(4)}",
                    raw_text=raw,
                    effect="ALLOW",
                    action_types=["read", "view", "list"],
                    path_pattern="C:\\*",
                    risk_level="low",
                )
            )

        # Pattern 3: Create / edit inside a specific folder (e.g. D:\Projects)
        m_dir = re.search(r"(?:inside|in|to)\s+([a-zA-Z]:\\[a-zA-Z0-9_\-\\]+)", raw, re.IGNORECASE)
        if m_dir:
            target_dir = m_dir.group(1).rstrip("\\") + "\\*"
            is_denied = any(r.effect == "DENY" and r.path_pattern.lower() == target_dir.lower() for r in rules)
            is_negated = any(neg in low for neg in ("cannot", "can't", "don't", "do not", "block", "deny")) and ("windows" in target_dir.lower() or "c:\\" in target_dir.lower())
            if not is_denied and not is_negated and any(w in low for w in ("create", "edit", "write", "modify", "add")):
                rules.append(
                    CustomRule(
                        id=f"rule_allow_write_{secrets.token_hex(4)}",
                        raw_text=raw,
                        effect="ALLOW",
                        action_types=["create", "write", "edit", "modify", "touch"],
                        path_pattern=target_dir,
                        risk_level="medium",
                    )
                )

        # Pattern 4: Ask permission before deleting
        if any(w in low for w in ("ask", "permission", "confirm")) and any(w in low for w in ("delete", "deleting", "remove")):
            path_pat = "*"
            if m_dir:
                path_pat = m_dir.group(1).rstrip("\\") + "\\*"
            rules.append(
                CustomRule(
                    id=f"rule_ask_delete_{secrets.token_hex(4)}",
                    raw_text=raw,
                    effect="ASK",
                    action_types=["delete", "remove", "unlink", "cleanup"],
                    path_pattern=path_pat,
                    risk_level="high",
                )
            )

        # Generic fallback if no specific pattern matched
        if not rules:
            effect = "DENY" if any(w in low for w in ("cannot", "can't", "deny", "block", "no")) else "ALLOW"
            actions = ["*"]
            if "delete" in low:
                actions = ["delete"]
            elif "write" in low or "create" in low:
                actions = ["write", "create"]
            elif "read" in low:
                actions = ["read"]

            path_pat = "*"
            m_any_path = re.search(r"([a-zA-Z]:\\[^\s,]+)", raw)
            if m_any_path:
                path_pat = m_any_path.group(1).rstrip("\\") + "\\*"

            rules.append(
                CustomRule(
                    id=f"rule_custom_{secrets.token_hex(4)}",
                    raw_text=raw,
                    effect=effect,
                    action_types=actions,
                    path_pattern=path_pat,
                    risk_level="medium",
                )
            )

        return rules

    def evaluate(self, action_type: str, path: str) -> Tuple[Optional[str], Optional[CustomRule]]:
        """Evaluate custom rules in strict precedence order: DENY > ASK > ALLOW."""
        # 1. Deny rules take highest custom precedence
        for r in self._rules:
            if r.effect == "DENY" and r.matches(action_type, path):
                return "DENY", r

        # 2. Ask rules take next precedence
        for r in self._rules:
            if r.effect == "ASK" and r.matches(action_type, path):
                return "ASK", r

        # 3. Allow rules
        for r in self._rules:
            if r.effect == "ALLOW" and r.matches(action_type, path):
                return "ALLOW", r

        return None, None


# ---------------------------------------------------------------------------
# 3. Central Safety Kernel Controller
# ---------------------------------------------------------------------------

class SafetyKernel:
    """Central non-bypassable safety enforcement kernel."""

    # Absolute platform security invariants (never overridable by safety code or custom rules)
    CRITICAL_PATH_PATTERNS = [
        r"^[a-zA-Z]:\\windows(?:\\[^\s]*)?$",
        r"^[a-zA-Z]:\\system32(?:\\[^\s]*)?$",
        r"^[a-zA-Z]:\\boot(?:\\[^\s]*)?$",
        r"^[a-zA-Z]:\\recovery(?:\\[^\s]*)?$",
        r"^[a-zA-Z]:\\\$recycle\.bin(?:\\[^\s]*)?$",
        r"^/(?:etc|bin|sbin|boot|root|sys|proc)(?:/.*)?$",
        r"^[a-zA-Z]:\\(?:etc|bin|sbin|boot|root|sys|proc)(?:\\[^\s]*)?$",
    ]

    CRITICAL_SHELL_PATTERNS = [
        r"\bformat\s+[a-zA-Z]:",
        r"\bdiskpart\b",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r"\brm\s+-rf\s+(?:/|[a-zA-Z]:\\)",
        r"\bdel\s+/[a-z\s]*c:\\windows\b",
    ]

    def __init__(
        self,
        code_manager: Optional[SafetyCodeManager] = None,
        rules_engine: Optional[CustomRuleEngine] = None,
    ) -> None:
        self.code_mgr = code_manager or SafetyCodeManager()
        self.rules_engine = rules_engine or CustomRuleEngine()

    def evaluate(
        self,
        action_type: str,
        target: str = "",
        params: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyDecision:
        """Central evaluation gateway for all actions across the system."""
        act = (action_type or "").lower().strip()
        tgt = (target or "").strip()
        params = params or {}
        fingerprint = self.code_mgr.compute_fingerprint(act, tgt, params)

        # ── 1. Check Platform Critical Hard Blocks ──────────────────────────────
        # Shell command critical check
        if act in ("shell", "shell_exec", "command_exec"):
            cmd = params.get("command", tgt).lower()
            for pat in self.CRITICAL_SHELL_PATTERNS:
                if re.search(pat, cmd):
                    return SafetyDecision(
                        effect=ActionEffect.BLOCK,
                        risk_level=RiskLevel.CRITICAL,
                        reason="Fundamental Security Boundary: Dangerous destructive system command is permanently blocked.",
                        action_type=act,
                        target=tgt,
                        fingerprint=fingerprint,
                    )

        # Path-based critical check
        if tgt:
            norm_tgt = str(Path(tgt).resolve(strict=False))
            for pat in self.CRITICAL_PATH_PATTERNS:
                if re.match(pat, norm_tgt, flags=re.IGNORECASE) or re.match(pat, tgt, flags=re.IGNORECASE):
                    if any(a in act for a in ("write", "create", "delete", "modify", "edit", "patch")):
                        return SafetyDecision(
                            effect=ActionEffect.BLOCK,
                            risk_level=RiskLevel.CRITICAL,
                            reason=f"Fundamental Security Boundary: Modifications to protected operating system directory ({norm_tgt}) are strictly blocked.",
                            action_type=act,
                            target=tgt,
                            fingerprint=fingerprint,
                        )

        # ── 2. Check Custom Rules (DENY > ASK > ALLOW) ──────────────────────────
        if tgt:
            effect, rule = self.rules_engine.evaluate(act, tgt)
            if effect == "DENY":
                return SafetyDecision(
                    effect=ActionEffect.BLOCK,
                    risk_level=RiskLevel.HIGH,
                    reason=f"Custom Safety Rule Violation (Rule {rule.id}): Explicit deny rule blocked this action.",
                    action_type=act,
                    target=tgt,
                    fingerprint=fingerprint,
                    rule_id=rule.id if rule else None,
                )
            elif effect == "ASK":
                requires_code = self.code_mgr.is_code_set()
                return SafetyDecision(
                    effect=ActionEffect.ASK_WITH_CODE if requires_code else ActionEffect.ASK,
                    risk_level=RiskLevel.HIGH,
                    reason=f"Custom Safety Rule Requirement (Rule {rule.id}): User approval required before proceeding.",
                    action_type=act,
                    target=tgt,
                    fingerprint=fingerprint,
                    rule_id=rule.id if rule else None,
                    requires_code=requires_code,
                )
            elif effect == "ALLOW":
                return SafetyDecision(
                    effect=ActionEffect.ALLOW,
                    risk_level=RiskLevel.LOW,
                    reason=f"Authorized by Custom Safety Rule ({rule.id}).",
                    action_type=act,
                    target=tgt,
                    fingerprint=fingerprint,
                    rule_id=rule.id if rule else None,
                )

        # Shell high-risk operations
        if act in ("shell", "shell_exec", "command_exec"):
            cmd = params.get("command", tgt).lower()
            if any(re.search(pat, cmd) for pat in (
                r"\bdel\b", r"\brmdir\b", r"\brd\b", r"\bremove-item\b", r"\brm\s+",
                r"\breg\s+(?:add|delete)\b", r"\btakeown\b", r"\bicacls\b"
            )):
                requires_code = self.code_mgr.is_code_set()
                return SafetyDecision(
                    effect=ActionEffect.ASK_WITH_CODE if requires_code else ActionEffect.ASK,
                    risk_level=RiskLevel.HIGH,
                    reason="High Risk Shell Action: Destructive or system modifying command requires user approval.",
                    action_type=act,
                    target=tgt,
                    fingerprint=fingerprint,
                    requires_code=requires_code,
                )

        # Deletions / File cleanups: High Risk (requires preview, approval, and safety code if configured)
        if any(w in act for w in ("delete", "remove", "unlink", "cleanup", "erase", "purge")):
            preview = None
            if tgt:
                preview = self.preview_cleanup([tgt])
            requires_code = self.code_mgr.is_code_set()
            return SafetyDecision(
                effect=ActionEffect.ASK_WITH_CODE if requires_code else ActionEffect.ASK,
                risk_level=RiskLevel.HIGH,
                reason="Destructive Action: File cleanup or deletion requires explicit user confirmation and safety code.",
                action_type=act,
                target=tgt,
                fingerprint=fingerprint,
                preview=preview,
                requires_code=requires_code,
            )

        # C-Drive Root Modifications without custom rule: Blocked by default baseline
        if tgt:
            try:
                resolved = Path(tgt).resolve(strict=False)
                if resolved.drive.upper() == "C:" and any(w in act for w in ("write", "create", "modify", "edit")):
                    # Check if inside user profile or temp (which may be allowed under medium risk)
                    user_profile = str(Path.home()).lower()
                    if str(resolved).lower().startswith(user_profile):
                        return SafetyDecision(
                            effect=ActionEffect.ALLOW,
                            risk_level=RiskLevel.MEDIUM,
                            reason="Authorized user profile storage write.",
                            action_type=act,
                            target=tgt,
                            fingerprint=fingerprint,
                        )
                    return SafetyDecision(
                        effect=ActionEffect.BLOCK,
                        risk_level=RiskLevel.HIGH,
                        reason="C-Drive System Isolation: Write access outside user profile on C: drive is restricted.",
                        action_type=act,
                        target=tgt,
                        fingerprint=fingerprint,
                    )
            except Exception:
                pass

        # Safe Workspace Writes (D:, E:, etc.): Medium Risk (executes automatically if safe)
        if any(w in act for w in ("write", "create", "append", "modify", "edit", "patch")):
            return SafetyDecision(
                effect=ActionEffect.ALLOW,
                risk_level=RiskLevel.MEDIUM,
                reason="Safe workspace filesystem write.",
                action_type=act,
                target=tgt,
                fingerprint=fingerprint,
            )

        # App Launching & Explorer Exploration: Low Risk
        if act in ("app_launch", "open_drive", "open_folder", "media_play", "chrome_profile_navigate"):
            return SafetyDecision(
                effect=ActionEffect.ALLOW,
                risk_level=RiskLevel.LOW,
                reason="Safe application or desktop navigation action.",
                action_type=act,
                target=tgt,
                fingerprint=fingerprint,
            )

        # Read-only / Query: Low Risk
        return SafetyDecision(
            effect=ActionEffect.ALLOW,
            risk_level=RiskLevel.LOW,
            reason="Read-only or low-risk query authorized automatically.",
            action_type=act,
            target=tgt,
            fingerprint=fingerprint,
        )

    def preview_cleanup(self, targets: List[Any]) -> Dict[str, Any]:
        """Generate an exact impact preview for file cleanups."""
        file_items: List[Dict[str, Any]] = []
        total_bytes = 0

        for t in targets:
            p = Path(t)
            if p.is_file():
                sz = p.stat().st_size if p.exists() else 0
                file_items.append({"path": str(p), "name": p.name, "size_bytes": sz, "type": "file"})
                total_bytes += sz
            elif p.is_dir():
                try:
                    for sub in p.glob("**/*"):
                        if sub.is_file():
                            sz = sub.stat().st_size
                            file_items.append({"path": str(sub), "name": sub.name, "size_bytes": sz, "type": "file"})
                            total_bytes += sz
                except Exception:
                    pass

        destination = "Windows Recycle Bin" if sys.platform == "win32" else "Quarantine Directory"
        return {
            "total_files": len(file_items),
            "total_bytes": total_bytes,
            "destination": destination,
            "target_samples": file_items[:20],
        }

    def safe_delete_or_quarantine(self, target_path: Path | str) -> Tuple[bool, str]:
        """Safely remove a file by moving it to the Windows Recycle Bin or Quarantine directory."""
        p = Path(target_path).resolve(strict=False)
        if not p.exists():
            return False, f"Target file does not exist: {p}"

        # 1. On Windows, attempt native Shell Recycle Bin (SHFileOperation)
        if sys.platform == "win32":
            try:
                # FO_DELETE = 3, FOF_ALLOWUNDO = 0x0040, FOF_NOCONFIRMATION = 0x0010, FOF_SILENT = 0x0004
                class SHFILEOPSTRUCTW(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", ctypes.c_void_p),
                        ("wFunc", ctypes.c_uint),
                        ("pFrom", ctypes.c_wchar_p),
                        ("pTo", ctypes.c_wchar_p),
                        ("fFlags", ctypes.c_ushort),
                        ("fAnyOperationsAborted", ctypes.c_bool),
                        ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", ctypes.c_wchar_p),
                    ]

                path_double_null = str(p) + "\0\0"
                fileop = SHFILEOPSTRUCTW()
                fileop.wFunc = 3  # FO_DELETE
                fileop.pFrom = path_double_null
                fileop.fFlags = 0x0040 | 0x0010 | 0x0004  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

                res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
                if res == 0 and not fileop.fAnyOperationsAborted:
                    return True, f"File successfully moved to Windows Recycle Bin: {p.name}"
            except Exception as exc:
                logger.warning("Windows Recycle Bin failed, falling back to quarantine: %s", exc)

        # 2. Quarantine directory fallback
        quarantine_dir = get_config_dir() / "quarantine"
        try:
            import shutil

            quarantine_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time())
            quarantined_path = quarantine_dir / f"{timestamp}_{p.name}"
            shutil.move(str(p), str(quarantined_path))
            return True, f"File moved to safe quarantine: {quarantined_path}"
        except Exception as exc:
            return False, f"Failed to quarantine file {p.name}: {exc}"


# Global singleton instance
_GLOBAL_SAFETY_KERNEL = SafetyKernel()


def get_safety_kernel() -> SafetyKernel:
    """Return the global SafetyKernel singleton."""
    return _GLOBAL_SAFETY_KERNEL
