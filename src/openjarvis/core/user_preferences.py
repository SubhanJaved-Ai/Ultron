"""User preferences and address/honorific management for OpenJarvis/Ultron."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from openjarvis.core import paths

logger = logging.getLogger(__name__)


def _get_pref_file() -> Path:
    config_dir = paths.get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "user_preferences.json"


def get_user_address(user_id: str | None = None) -> str:
    """Return the user's preferred address/title, or '' if not yet configured."""
    if user_id and user_id != "default":
        try:
            from openjarvis.auth.manager import get_user_manager

            val = get_user_manager().get_preference(user_id, "preferred_address")
            if val:
                return str(val).strip()
        except Exception:
            pass

    # 1. Check user_preferences.json
    f = _get_pref_file()
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            val = str(data.get("preferred_address") or "").strip()
            if val:
                return val
        except Exception:
            pass

    # 2. Fallback to USER.md inspection
    user_md = paths.get_config_dir() / "USER.md"
    if user_md.is_file():
        try:
            for raw_line in user_md.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line.lower().startswith(("- call me:", "* call me:")):
                    parts = line.split(":", 1)
                    if len(parts) > 1 and parts[1].strip():
                        return parts[1].strip()
                elif line.lower().startswith(("- call me", "* call me")):
                    parts = line.split("call me", 1)
                    if len(parts) > 1 and parts[1].strip():
                        return parts[1].strip().lstrip(" :")
                elif line.lower().startswith(
                    ("- preferred address:", "* preferred address:")
                ):
                    parts = line.split(":", 1)
                    if len(parts) > 1 and parts[1].strip():
                        return parts[1].strip()
        except Exception:
            pass

    return ""


def set_user_address(address: str, user_id: str | None = None) -> str:
    """Save the user's preferred title or name in user_preferences.json/USER.md or DB."""
    clean = (address or "").strip()
    if not clean:
        return ""

    # Clean punctuation and polite wrappers
    clean = re.sub(
        r"^(?:please\s+|just\s+)?",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    clean = clean.rstrip(".,!?:;").strip()

    # Security sanitization: strip newlines, HTML tags, markdown controls, and cap length
    clean = re.sub(r"[<>\r\n#*_`\[\]]", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > 48:
        clean = clean[:48].strip()

    if not clean:
        return ""

    if user_id and user_id != "default":
        try:
            from openjarvis.auth.manager import get_user_manager

            get_user_manager().set_preference(user_id, "preferred_address", clean)
            return clean
        except Exception as exc:
            logger.debug("Failed to set per-user address preference: %s", exc)

    # Save to user_preferences.json
    f = _get_pref_file()
    data: dict[str, str] = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["preferred_address"] = clean
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Sync to USER.md
    user_md = paths.get_config_dir() / "USER.md"
    try:
        content = (
            user_md.read_text(encoding="utf-8")
            if user_md.is_file()
            else "# User Profile\n\n"
        )
        lines = [
            line
            for line in content.splitlines()
            if not any(k in line.lower() for k in ("call me", "preferred address"))
        ]
        lines.append(f"- Preferred Address: {clean}")
        user_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not sync address to USER.md: %s", exc)

    return clean


def format_addressed(sentence: str) -> str:
    """Format a sentence with the user's address if known, or neutrally if not."""
    title = get_user_address()
    clean = sentence.strip()
    # Strip any hardcoded default trailing ", sir." or ", sir"
    clean = re.sub(r",\s*sir\b\.?", "", clean, flags=re.IGNORECASE).rstrip(".,! ")
    if title:
        return f"{clean}, {title}."
    return f"{clean}."
