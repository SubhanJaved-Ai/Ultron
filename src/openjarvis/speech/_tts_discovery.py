"""Auto-discover available text-to-speech backends.

Mirrors ``speech/_discovery.py``, which does the same for speech-to-text. The
selection rules used to live in ``cli/_voice_chat.py``; they moved here so the
API server can reuse them instead of importing from the CLI package.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from openjarvis.core.config import JarvisConfig

logger = logging.getLogger(__name__)

# Priority order: local first, then cloud.
TTS_BACKEND_ORDER = ("kokoro", "elevenlabs", "openai_tts", "cartesia")

# Voice IDs are backend-specific and NOT portable. ``speech.voice_id`` applies
# only to ``speech.tts_backend``; if synthesis falls back to another backend we
# use that backend's own default rather than passing an unrecognized ID through.
BACKEND_DEFAULT_VOICE = {
    "kokoro": "bm_george",  # British male
    "elevenlabs": "JBFqnCBsd6RMkjVDRZzb",  # British Jarvis preset
    "openai_tts": "onyx",  # deepest OpenAI preset
    "cartesia": "",  # no safe static default; let Cartesia choose
}


def default_voice_for(backend_id: str) -> str:
    """Return the fallback voice ID for *backend_id*, or an empty string."""
    return BACKEND_DEFAULT_VOICE.get(backend_id, "")


def get_tts_backend(
    preferred: str = "",
    *,
    attempted: Optional[set[str]] = None,
) -> Optional[Any]:
    """Return the first healthy TTS backend, preferring *preferred*.

    ``attempted`` lets a caller carry state across calls so a backend that
    already failed is not retried; it is mutated in place.
    """
    # Import triggers built-in backend registration only when voice output is
    # actually requested.
    import openjarvis.speech  # noqa: F401
    from openjarvis.core.registry import TTSRegistry

    try:
        from openjarvis.speech.elevenlabs_tts import ensure_registered as _ensure_el

        _ensure_el()
    except ImportError:
        pass

    seen = attempted if attempted is not None else set()

    effective_preferred = preferred
    if not effective_preferred:
        try:
            from openjarvis.core.user_preferences import get_voice_preferences

            vprefs = get_voice_preferences()
            prov = vprefs.get("provider", "")
            if prov and prov != "system":
                effective_preferred = prov
        except Exception:
            pass

    for key in dict.fromkeys((effective_preferred, *TTS_BACKEND_ORDER)):
        if not key or key in seen:
            continue
        seen.add(key)
        if not TTSRegistry.contains(key):
            continue
        try:
            candidate = TTSRegistry.get(key)()
            if candidate.health():
                return candidate
        except Exception:
            logger.debug("TTS backend %s unavailable", key, exc_info=True)
            continue
    return None


def voice_preferences(config: "JarvisConfig") -> tuple[str, str, float]:
    """Resolve ``(tts_backend, voice_id, speed)`` from *config* and user preferences."""
    try:
        from openjarvis.core.user_preferences import get_voice_preferences

        vprefs = get_voice_preferences()
        if vprefs.get("provider") == "elevenlabs":
            return (
                "elevenlabs",
                vprefs.get("voice_id") or BACKEND_DEFAULT_VOICE["elevenlabs"],
                float(vprefs.get("speed", 1.0)),
            )
    except Exception:
        pass

    speech = getattr(config, "speech", None)
    return (
        getattr(speech, "tts_backend", "kokoro") or "kokoro",
        getattr(speech, "voice_id", "") or "",
        float(getattr(speech, "voice_speed", 1.0)),
    )



__all__ = [
    "BACKEND_DEFAULT_VOICE",
    "TTS_BACKEND_ORDER",
    "default_voice_for",
    "get_tts_backend",
    "voice_preferences",
]
