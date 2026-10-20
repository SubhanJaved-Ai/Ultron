"""User preferences, address/honorific management, and personality controls for OpenJarvis/Ultron."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from openjarvis.core import paths

logger = logging.getLogger(__name__)


USER_PREFERENCES_PATH: Path | None = None


def _get_pref_file() -> Path:
    if USER_PREFERENCES_PATH is not None:
        return Path(USER_PREFERENCES_PATH)
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


# ---------------------------------------------------------------------------
# Personality Controls (TSK-P5-02 — Soul Circuit)
# ---------------------------------------------------------------------------

#: Dimensions and their neutral defaults.
PERSONALITY_DIMENSIONS = ("formality", "verbosity", "warmth")
_PERSONALITY_DEFAULTS: dict[str, float] = {
    "formality": 0.5,
    "verbosity": 0.5,
    "warmth": 0.5,
}


def _validate_personality_float(value: object) -> float:
    """Return a clean float in [0.0, 1.0] or raise ValueError."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Personality value must be a number, got: {value!r}") from exc
    import math

    if not math.isfinite(v):
        raise ValueError(f"Personality value must be finite, got: {v!r}")
    if not (0.0 <= v <= 1.0):
        raise ValueError(
            f"Personality value must be in [0.0, 1.0], got: {v!r}"
        )
    return round(v, 4)


def get_personality() -> dict[str, float]:
    """Return the current personality settings (Formality, Verbosity, Warmth).

    Always returns a complete dict with all three keys; missing or corrupt
    values fall back to the neutral default of 0.5.
    """
    result = dict(_PERSONALITY_DEFAULTS)
    f = _get_pref_file()
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pref = data.get("personality") or {}
            if isinstance(pref, dict):
                for dim in PERSONALITY_DIMENSIONS:
                    raw = pref.get(dim)
                    if raw is not None:
                        try:
                            result[dim] = _validate_personality_float(raw)
                        except ValueError:
                            pass  # keep default on invalid persisted value
        except Exception:
            pass
    return result


def set_personality(updates: dict[str, float]) -> dict[str, float]:
    """Persist personality dimension updates and return the merged settings.

    Only keys listed in PERSONALITY_DIMENSIONS are accepted.  Every value
    is validated as a finite float in [0.0, 1.0].  Unknown keys and
    injection payloads are silently discarded.

    Args:
        updates: Mapping of dimension name → float value in [0.0, 1.0].

    Returns:
        The full, merged personality dict after saving.

    Raises:
        ValueError: If any accepted dimension value fails validation.
    """
    # Validate accepted keys only — reject unknown/injection keys
    sanitized: dict[str, float] = {}
    for dim in PERSONALITY_DIMENSIONS:
        if dim in updates:
            sanitized[dim] = _validate_personality_float(updates[dim])

    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    existing_pref: dict[str, float] = {}
    if isinstance(data.get("personality"), dict):
        for dim in PERSONALITY_DIMENSIONS:
            raw = data["personality"].get(dim)
            if raw is not None:
                try:
                    existing_pref[dim] = _validate_personality_float(raw)
                except ValueError:
                    pass

    merged = {**_PERSONALITY_DEFAULTS, **existing_pref, **sanitized}
    data["personality"] = merged
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Personality settings updated: %s", merged)
    return merged


# ---------------------------------------------------------------------------
# Theme Controls (TSK-P5-03 — Tri-Theme Hologram HUD)
# ---------------------------------------------------------------------------

VALID_THEMES = ("cyan", "crimson", "emerald")
DEFAULT_THEME = "cyan"


def _validate_theme(value: object) -> str:
    """Validate theme name against allowed options.

    Returns normalized lower-case theme string, or raises ValueError.
    """
    if not isinstance(value, str):
        raise ValueError(f"Theme must be a string, got: {type(value).__name__}")
    t = value.strip().lower()
    if t not in VALID_THEMES:
        raise ValueError(
            f"Invalid theme {value!r}. Must be one of: {', '.join(VALID_THEMES)}"
        )
    return t


def get_theme(user_id: str | None = None) -> str:
    """Return the currently selected hologram theme (cyan, crimson, emerald).

    Falls back to DEFAULT_THEME ('cyan') if not configured or corrupt.
    """
    if user_id and user_id != "default":
        try:
            from openjarvis.auth.manager import get_user_manager

            val = get_user_manager().get_preference(user_id, "hologram_theme")
            if val:
                return _validate_theme(val)
        except Exception:
            pass

    f = _get_pref_file()
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            raw = data.get("theme")
            if raw is not None:
                return _validate_theme(raw)
        except Exception:
            pass

    return DEFAULT_THEME


def set_theme(theme: str, user_id: str | None = None) -> str:
    """Validate and persist the hologram HUD theme.

    Args:
        theme: One of 'cyan', 'crimson', or 'emerald' (case-insensitive).
        user_id: Optional user identifier for multi-tenant preference storage.

    Returns:
        The normalized theme string saved.

    Raises:
        ValueError: If theme is invalid or not in VALID_THEMES.
    """
    validated = _validate_theme(theme)

    if user_id and user_id != "default":
        try:
            from openjarvis.auth.manager import get_user_manager

            get_user_manager().set_preference(user_id, "hologram_theme", validated)
        except Exception as exc:
            logger.debug("Failed to set per-user theme preference: %s", exc)

    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["theme"] = validated
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Hologram theme updated: %s", validated)
    return validated


# ---------------------------------------------------------------------------
# Voice & ElevenLabs Preferences
# ---------------------------------------------------------------------------

VALID_VOICE_PROVIDERS = ("system", "elevenlabs", "kokoro", "openai_tts", "cartesia")
DEFAULT_VOICE_PROVIDER = "system"
DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_ELEVENLABS_MODEL = "eleven_turbo_v2_5"

_VOICE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_MODEL_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")


def mask_api_key(key: str) -> str:
    """Return a masked representation of an API key, revealing at most 4 trailing chars."""
    if not key:
        return ""
    clean = key.strip()
    if len(clean) <= 4:
        return "••••••••"
    return "••••••••" + clean[-4:]


def get_elevenlabs_api_key() -> str:
    """Retrieve ElevenLabs API key from process environment or cloud-keys.env."""
    import os

    for env_var in ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    # Check ~/.openjarvis/cloud-keys.env
    env_file = paths.get_config_dir() / "cloud-keys.env"
    if env_file.is_file():
        try:
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() in ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
                        val = v.strip()
                        if val:
                            return val
        except Exception:
            pass

    return ""


def save_elevenlabs_api_key(key: str) -> None:
    """Save ElevenLabs API key server-side into environment and cloud-keys.env."""
    import os

    clean_key = (key or "").strip()
    if clean_key:
        os.environ["ELEVENLABS_API_KEY"] = clean_key
    else:
        os.environ.pop("ELEVENLABS_API_KEY", None)
        os.environ.pop("ELEVEN_API_KEY", None)

    env_file = paths.get_config_dir() / "cloud-keys.env"
    lines = []
    found = False
    if env_file.is_file():
        try:
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _ = line.split("=", 1)
                    if k.strip() in ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
                        if clean_key:
                            lines.append(f"ELEVENLABS_API_KEY={clean_key}")
                        found = True
                        continue
                lines.append(raw_line)
        except Exception:
            lines = []

    if clean_key and not found:
        lines.append(f"ELEVENLABS_API_KEY={clean_key}")

    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def get_voice_preferences(user_id: str | None = None) -> dict:
    """Return voice preferences dictionary with masked API key info."""
    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    voice_data = data.get("voice", {})
    provider = voice_data.get("provider", DEFAULT_VOICE_PROVIDER)
    if provider not in VALID_VOICE_PROVIDERS:
        provider = DEFAULT_VOICE_PROVIDER

    key = get_elevenlabs_api_key()
    has_key = bool(key)
    masked_key = mask_api_key(key)

    return {
        "provider": provider,
        "voice_id": str(voice_data.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)),
        "model_id": str(voice_data.get("model_id", DEFAULT_ELEVENLABS_MODEL)),
        "stability": float(voice_data.get("stability", 0.5)),
        "similarity_boost": float(voice_data.get("similarity_boost", 0.75)),
        "style": float(voice_data.get("style", 0.0)),
        "speed": float(voice_data.get("speed", 1.0)),
        "has_api_key": has_key,
        "masked_api_key": masked_key,
    }


def set_voice_preferences(updates: dict, user_id: str | None = None) -> dict:
    """Validate and persist voice preferences in user_preferences.json."""
    if not isinstance(updates, dict):
        raise ValueError("Payload must be a dictionary")

    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    current = data.get("voice", {})

    if "provider" in updates:
        prov = str(updates["provider"]).strip().lower()
        if prov not in VALID_VOICE_PROVIDERS:
            raise ValueError(f"Invalid voice provider: {prov}")
        current["provider"] = prov

    if "voice_id" in updates:
        vid = str(updates["voice_id"]).strip()
        if not _VOICE_ID_RE.match(vid):
            raise ValueError(f"Invalid voice_id format: {vid}")
        current["voice_id"] = vid

    if "model_id" in updates:
        mid = str(updates["model_id"]).strip()
        if not _MODEL_ID_RE.match(mid):
            raise ValueError(f"Invalid model_id format: {mid}")
        current["model_id"] = mid

    if "stability" in updates:
        stab = float(updates["stability"])
        if not (0.0 <= stab <= 1.0):
            raise ValueError("Stability must be between 0.0 and 1.0")
        current["stability"] = stab

    if "similarity_boost" in updates:
        sim = float(updates["similarity_boost"])
        if not (0.0 <= sim <= 1.0):
            raise ValueError("Similarity boost must be between 0.0 and 1.0")
        current["similarity_boost"] = sim

    if "style" in updates:
        sty = float(updates["style"])
        if not (0.0 <= sty <= 1.0):
            raise ValueError("Style must be between 0.0 and 1.0")
        current["style"] = sty

    if "speed" in updates:
        spd = float(updates["speed"])
        if not (0.5 <= spd <= 2.0):
            raise ValueError("Speed must be between 0.5 and 2.0")
        current["speed"] = spd

    data["voice"] = current
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Voice preferences updated: provider=%s", current.get("provider"))
    return get_voice_preferences(user_id=user_id)


def get_model_preferences(user_id: str | None = None) -> dict:
    """Return model selection preferences including rollback history."""
    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    model_data = data.get("model_selection", {})
    return {
        "provider": str(model_data.get("provider", "cloud")),
        "model": str(model_data.get("model", "gemini-3.8-flash")),
        "previous_provider": str(model_data.get("previous_provider", "")),
        "previous_model": str(model_data.get("previous_model", "")),
        "updated_at": float(model_data.get("updated_at", 0.0)),
    }


def set_model_preferences(provider: str, model: str, user_id: str | None = None) -> dict:
    """Update active model, safely preserving previous configuration for 1-click rollback."""
    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    current = data.get("model_selection", {})
    prev_prov = current.get("provider", "cloud")
    prev_mod = current.get("model", "gemini-3.8-flash")

    new_sel = {
        "provider": str(provider).strip().lower(),
        "model": str(model).strip(),
        "previous_provider": prev_prov,
        "previous_model": prev_mod,
        "updated_at": time.time(),
    }

    data["model_selection"] = new_sel
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Model preferences updated: %s / %s (previous: %s / %s)", provider, model, prev_prov, prev_mod)
    return new_sel


def rollback_model_preferences(user_id: str | None = None) -> dict:
    """Restore the previous model and provider configuration."""
    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    current = data.get("model_selection", {})
    prev_prov = current.get("previous_provider")
    prev_mod = current.get("previous_model")

    if not prev_prov or not prev_mod:
        raise ValueError("No previous model configuration available to roll back to.")

    return set_model_preferences(provider=prev_prov, model=prev_mod, user_id=user_id)


# ---------------------------------------------------------------------------
# Personalization & Persona Voice Experience
# ---------------------------------------------------------------------------

VALID_PERSONAS = (
    "jarvis",
    "assistant",
    "mentor",
    "best_friend",
    "bro",
    "listener",
    "partner",
    "core",
)
DEFAULT_PERSONA = "jarvis"

VALID_PRESENTATIONS = ("masculine", "feminine", "neutral")
DEFAULT_PRESENTATION = "neutral"

VALID_VOICE_GENDERS = ("masculine", "feminine", "neutral")
DEFAULT_VOICE_GENDER = "masculine"

VALID_LANGUAGES = ("en", "ur", "hi", "auto")
DEFAULT_LANGUAGE = "en"

_PHONE_RE = re.compile(r"^[\+]?[0-9\s\-\(\)]{0,24}$")


def _validate_persona(val: object) -> str:
    clean = str(val or "").strip().lower()
    if clean not in VALID_PERSONAS:
        raise ValueError(
            f"Invalid persona '{val}'. Must be one of: {', '.join(VALID_PERSONAS)}"
        )
    return clean


def _validate_presentation(val: object) -> str:
    clean = str(val or "").strip().lower()
    if clean not in VALID_PRESENTATIONS:
        raise ValueError(
            f"Invalid presentation '{val}'. Must be one of: {', '.join(VALID_PRESENTATIONS)}"
        )
    return clean


def _validate_voice_gender(val: object) -> str:
    clean = str(val or "").strip().lower()
    if clean not in VALID_VOICE_GENDERS:
        raise ValueError(
            f"Invalid voice gender '{val}'. Must be one of: {', '.join(VALID_VOICE_GENDERS)}"
        )
    return clean


def _validate_language(val: object) -> str:
    clean = str(val or "").strip().lower()
    if clean not in VALID_LANGUAGES:
        raise ValueError(
            f"Invalid language '{val}'. Must be one of: {', '.join(VALID_LANGUAGES)}"
        )
    return clean


def get_personalization_preferences(user_id: str | None = None) -> dict:
    """Return personalization settings: persona, presentation, language, sound effects, name."""
    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    pers_data = data.get("personalization", {})
    if not isinstance(pers_data, dict):
        pers_data = {}

    persona = pers_data.get("persona", DEFAULT_PERSONA)
    if persona not in VALID_PERSONAS:
        persona = DEFAULT_PERSONA

    # Voice output gender / timbre preference
    voice_gender = (
        pers_data.get("voice_gender")
        or pers_data.get("voice_presentation")
        or (pers_data.get("presentation") if pers_data.get("presentation") in VALID_VOICE_GENDERS else None)
        or DEFAULT_VOICE_GENDER
    )
    if voice_gender not in VALID_VOICE_GENDERS:
        voice_gender = DEFAULT_VOICE_GENDER

    # Ultron's visual hologram is always the single canonical Electron core
    presentation = DEFAULT_PRESENTATION

    language = pers_data.get("language", DEFAULT_LANGUAGE)
    if language not in VALID_LANGUAGES:
        language = DEFAULT_LANGUAGE

    sound_data = pers_data.get("sound_effects", {})
    if not isinstance(sound_data, dict):
        sound_data = {}

    if "sound_enabled" in pers_data:
        sound_enabled = bool(pers_data["sound_enabled"])
    else:
        sound_enabled = bool(sound_data.get("enabled", True))

    try:
        if "sound_volume" in pers_data:
            sound_vol = max(0.0, min(1.0, float(pers_data["sound_volume"])))
        else:
            sound_vol = max(0.0, min(1.0, float(sound_data.get("volume", 0.6))))
    except (ValueError, TypeError):
        sound_vol = 0.6

    user_name = get_user_address(user_id=user_id) or "Sir"
    phone = str(pers_data.get("notification_phone") or pers_data.get("phone_number") or "").strip()
    onboarding_completed = bool(pers_data.get("onboarding_completed", False))

    return {
        "user_name": user_name,
        "phone_number": phone,
        "notification_phone": phone,
        "presentation": presentation,
        "voice_presentation": voice_gender,
        "voice_gender": voice_gender,
        "persona": persona,
        "language": language,
        "sound_enabled": sound_enabled,
        "sound_volume": sound_vol,
        "sound_effects": {
            "enabled": sound_enabled,
            "volume": sound_vol,
        },
        "onboarding_completed": onboarding_completed,
    }


def set_personalization_preferences(updates: dict, user_id: str | None = None) -> dict:
    """Validate and persist personalization preferences in user_preferences.json."""
    if not isinstance(updates, dict):
        raise ValueError("Payload must be a dictionary")

    f = _get_pref_file()
    data: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    current = data.get("personalization", {})
    if not isinstance(current, dict):
        current = {}

    if "persona" in updates and updates["persona"] is not None:
        current["persona"] = _validate_persona(updates["persona"])

    # Voice gender / timbre preference
    gender_input = (
        updates.get("voice_gender")
        if "voice_gender" in updates
        else updates.get("voice_presentation")
        if "voice_presentation" in updates
        else updates.get("presentation")
    )
    if gender_input is not None:
        validated_gender = _validate_voice_gender(gender_input)
        current["voice_gender"] = validated_gender
        current["voice_presentation"] = validated_gender

    # Ultron's visual hologram is always the canonical Electron core
    current["presentation"] = DEFAULT_PRESENTATION

    if "language" in updates and updates["language"] is not None:
        current["language"] = _validate_language(updates["language"])

    phone_val = updates.get("phone_number") if "phone_number" in updates else updates.get("notification_phone")
    if phone_val is not None:
        clean_phone = str(phone_val).strip()
        if clean_phone and not _PHONE_RE.match(clean_phone):
            raise ValueError(f"Invalid phone number: {clean_phone}")
        current["notification_phone"] = clean_phone
        current["phone_number"] = clean_phone

    if "onboarding_completed" in updates and updates["onboarding_completed"] is not None:
        current["onboarding_completed"] = bool(updates["onboarding_completed"])

    curr_snd = current.get("sound_effects", {"enabled": True, "volume": 0.6})
    if not isinstance(curr_snd, dict):
        curr_snd = {"enabled": True, "volume": 0.6}

    if "sound_enabled" in updates and updates["sound_enabled"] is not None:
        curr_snd["enabled"] = bool(updates["sound_enabled"])
        current["sound_enabled"] = curr_snd["enabled"]

    if "sound_volume" in updates and updates["sound_volume"] is not None:
        try:
            curr_snd["volume"] = max(0.0, min(1.0, float(updates["sound_volume"])))
        except (ValueError, TypeError):
            curr_snd["volume"] = 0.6
        current["sound_volume"] = curr_snd["volume"]

    if "sound_effects" in updates and isinstance(updates["sound_effects"], dict):
        snd = updates["sound_effects"]
        if "enabled" in snd:
            curr_snd["enabled"] = bool(snd["enabled"])
            current["sound_enabled"] = curr_snd["enabled"]
        if "volume" in snd:
            try:
                curr_snd["volume"] = max(0.0, min(1.0, float(snd["volume"])))
            except (ValueError, TypeError):
                curr_snd["volume"] = 0.6
            current["sound_volume"] = curr_snd["volume"]

    current["sound_effects"] = curr_snd

    if "user_name" in updates and updates["user_name"] is not None:
        clean_name = str(updates["user_name"]).strip()
        set_user_address(clean_name, user_id=user_id)
        current["user_name"] = clean_name

    data["personalization"] = current
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Personalization preferences updated: persona=%s", current.get("persona"))

    return get_personalization_preferences(user_id=user_id)



