"""ElevenLabs text-to-speech backend.

Uses the ElevenLabs REST API for lifelike, cinematic voice synthesis.
Requires ELEVENLABS_API_KEY environment variable, config, or vault.
"""

from __future__ import annotations

import io
import logging
import os
import re
import wave
from typing import Any, Dict, List, Optional

import httpx
import time

from openjarvis.core.registry import TTSRegistry
from openjarvis.engine.resource_limiter import get_resource_limiter
from openjarvis.security.credential_stripper import sanitize_error_message
from openjarvis.speech.tts import TTSBackend, TTSResult
from openjarvis.traces.usage_ledger import get_usage_ledger

logger = logging.getLogger(__name__)

_ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_ELEVENLABS_MODEL = "eleven_turbo_v2_5"
# Classic British voice ("George" / "Adam" / "Jarvis" preset)
DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"

_VOICE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_MODEL_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")


class ElevenLabsError(Exception):
    """Base exception for ElevenLabs API errors."""

    pass


class ElevenLabsAuthError(ElevenLabsError):
    """Raised when ElevenLabs credentials are invalid or unauthorized (401/403)."""

    pass


class ElevenLabsQuotaError(ElevenLabsError):
    """Raised when ElevenLabs account hits quota exhaustion or rate limits (429)."""

    pass


class ElevenLabsTimeoutError(ElevenLabsError):
    """Raised when an ElevenLabs network request times out."""

    pass


class ElevenLabsAPIError(ElevenLabsError):
    """Raised when ElevenLabs upstream server returns an error response."""

    pass


def _handle_http_error(exc: httpx.HTTPStatusError) -> None:
    """Translate httpx status error to specific sanitized ElevenLabs exception."""
    status = exc.response.status_code
    text = exc.response.text
    sanitized = sanitize_error_message(text[:300])
    if status in (401, 403):
        raise ElevenLabsAuthError(
            f"ElevenLabs authentication failed ({status}): {sanitized}"
        ) from exc
    elif status == 429:
        raise ElevenLabsQuotaError(
            f"ElevenLabs quota or rate limit exceeded (429): {sanitized}"
        ) from exc
    elif status >= 500:
        raise ElevenLabsAPIError(
            f"ElevenLabs upstream server error ({status}): {sanitized}"
        ) from exc
    else:
        raise ElevenLabsAPIError(
            f"ElevenLabs API error ({status}): {sanitized}"
        ) from exc


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a standard RIFF/WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _elevenlabs_synthesize(
    api_key: str,
    text: str,
    voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID,
    model_id: str = DEFAULT_ELEVENLABS_MODEL,
    output_format: str = "mp3",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    timeout: float = 60.0,
    style: float = 0.0,
    speed: float = 1.0,
) -> bytes:
    """Call the ElevenLabs TTS API and return raw audio bytes."""
    clean_text = (text or "").strip()
    if not clean_text:
        raise ValueError("Text to synthesize cannot be empty.")
    if len(clean_text) > 5000:
        raise ValueError("Text exceeds maximum synthesis length of 5000 characters.")

    target_voice = voice_id or DEFAULT_ELEVENLABS_VOICE_ID
    if not _VOICE_ID_RE.match(target_voice):
        raise ValueError(f"Invalid voice ID format: {target_voice}")

    target_model = model_id or DEFAULT_ELEVENLABS_MODEL
    if not _MODEL_ID_RE.match(target_model):
        raise ValueError(f"Invalid model ID format: {target_model}")

    format_param = "mp3_44100_128" if output_format == "mp3" else "pcm_24000"
    url = (
        f"{_ELEVENLABS_API_BASE}/text-to-speech/{target_voice}?output_format={format_param}"
    )

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    voice_settings: Dict[str, Any] = {
        "stability": max(0.0, min(1.0, float(stability))),
        "similarity_boost": max(0.0, min(1.0, float(similarity_boost))),
        "use_speaker_boost": True,
    }
    if style > 0.0:
        voice_settings["style"] = max(0.0, min(1.0, float(style)))
    if speed != 1.0:
        voice_settings["speed"] = max(0.5, min(2.0, float(speed)))

    payload: Dict[str, Any] = {
        "text": clean_text,
        "model_id": target_model,
        "voice_settings": voice_settings,
    }

    limiter = get_resource_limiter()
    start_time = time.time()
    captured_req_id = None
    stream_status = "success"

    with limiter.acquire_slot_sync("elevenlabs"):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            captured_req_id = resp.headers.get("request-id") or resp.headers.get("x-request-id")
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            stream_status = "error"
            _handle_http_error(exc)
        except httpx.TimeoutException as exc:
            stream_status = "error"
            raise ElevenLabsTimeoutError("ElevenLabs speech synthesis timed out") from exc
        except httpx.RequestError as exc:
            stream_status = "error"
            raise ElevenLabsAPIError(
                f"Network error during speech synthesis: {sanitize_error_message(str(exc))}"
            ) from exc
        except Exception:
            stream_status = "error"
            raise
        finally:
            duration = time.time() - start_time
            try:
                get_usage_ledger().record_usage(
                    provider="elevenlabs",
                    model=target_model,
                    request_id=captured_req_id,
                    characters=len(clean_text),
                    duration_seconds=duration,
                    status=stream_status,
                    purpose="speech",
                    metadata={"voice_id": target_voice, "format": output_format, "model_id": target_model},
                )
            except Exception:
                pass

    raw_bytes = resp.content
    if output_format == "wav" and not raw_bytes.startswith(b"RIFF"):
        return _pcm_to_wav(raw_bytes, sample_rate=24000)

    return raw_bytes


def _fetch_voices(api_key: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch list of available voices from ElevenLabs."""
    if not api_key:
        return []
    url = f"{_ELEVENLABS_API_BASE}/voices"
    headers = {"xi-api-key": api_key}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _handle_http_error(exc)
    except httpx.TimeoutException as exc:
        raise ElevenLabsTimeoutError("Timed out fetching voices from ElevenLabs") from exc
    except httpx.RequestError as exc:
        raise ElevenLabsAPIError(
            f"Network error fetching voices: {sanitize_error_message(str(exc))}"
        ) from exc

    data = resp.json()
    voices = data.get("voices", [])
    result = []
    for v in voices:
        vid = v.get("voice_id")
        if vid:
            result.append(
                {
                    "voice_id": vid,
                    "name": v.get("name") or vid,
                    "category": v.get("category", ""),
                    "preview_url": v.get("preview_url", ""),
                    "labels": v.get("labels", {}),
                }
            )
    return result


def _fetch_models(api_key: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch list of available models from ElevenLabs filtered for TTS capability."""
    if not api_key:
        return []
    url = f"{_ELEVENLABS_API_BASE}/models"
    headers = {"xi-api-key": api_key}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _handle_http_error(exc)
    except httpx.TimeoutException as exc:
        raise ElevenLabsTimeoutError("Timed out fetching models from ElevenLabs") from exc
    except httpx.RequestError as exc:
        raise ElevenLabsAPIError(
            f"Network error fetching models: {sanitize_error_message(str(exc))}"
        ) from exc

    data = resp.json()
    models = data if isinstance(data, list) else data.get("models", [])
    tts_models = []
    for m in models:
        can_tts = m.get("can_do_text_to_speech", False)
        mid = m.get("model_id")
        if can_tts and mid:
            tts_models.append(
                {
                    "model_id": mid,
                    "name": m.get("name") or mid,
                    "description": m.get("description", ""),
                    "can_do_text_to_speech": True,
                    "can_be_finetuned": m.get("can_be_finetuned", False),
                }
            )
    return tts_models


def test_connection(api_key: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Test connection and validate an ElevenLabs API key against official endpoints."""
    clean_key = (api_key or "").strip()
    if not clean_key:
        return {
            "valid": False,
            "status": "unconfigured",
            "message": "ElevenLabs API key is not configured.",
            "voices_count": 0,
            "models_count": 0,
        }
    try:
        voices = _fetch_voices(clean_key, timeout=timeout)
        models = _fetch_models(clean_key, timeout=timeout)
        return {
            "valid": True,
            "status": "connected",
            "message": f"Successfully connected. Found {len(voices)} voices and {len(models)} TTS models.",
            "voices_count": len(voices),
            "models_count": len(models),
        }
    except ElevenLabsAuthError as exc:
        return {
            "valid": False,
            "status": "invalid_key",
            "message": sanitize_error_message(str(exc)),
            "voices_count": 0,
            "models_count": 0,
        }
    except ElevenLabsQuotaError as exc:
        return {
            "valid": False,
            "status": "quota_limited",
            "message": sanitize_error_message(str(exc)),
            "voices_count": 0,
            "models_count": 0,
        }
    except ElevenLabsTimeoutError as exc:
        return {
            "valid": False,
            "status": "timeout",
            "message": "Connection to ElevenLabs timed out.",
            "voices_count": 0,
            "models_count": 0,
        }
    except Exception as exc:
        return {
            "valid": False,
            "status": "error",
            "message": sanitize_error_message(str(exc)),
            "voices_count": 0,
            "models_count": 0,
        }


def ensure_registered() -> None:
    """Idempotently register ElevenLabs backend in TTSRegistry."""
    if not TTSRegistry.contains("elevenlabs"):
        TTSRegistry.register_value("elevenlabs", ElevenLabsTTSBackend)


@TTSRegistry.register("elevenlabs")
class ElevenLabsTTSBackend(TTSBackend):
    """ElevenLabs TTS backend — cinematic, custom voice cloning synthesis."""

    backend_id = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str = "",
        model_id: str = "",
        default_voice_id: str = "",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        speed: float = 1.0,
    ) -> None:
        from openjarvis.core.user_preferences import (
            get_elevenlabs_api_key,
            get_voice_preferences,
        )

        resolved_key = (
            api_key
            or get_elevenlabs_api_key()
            or os.environ.get("ELEVENLABS_API_KEY", "")
            or os.environ.get("ELEVEN_API_KEY", "")
        )
        self._api_key = resolved_key.strip()

        prefs: Dict[str, Any] = {}
        try:
            prefs = get_voice_preferences()
        except Exception:
            pass

        self._model_id = model_id or prefs.get("model_id") or DEFAULT_ELEVENLABS_MODEL
        self._default_voice_id = (
            default_voice_id or prefs.get("voice_id") or DEFAULT_ELEVENLABS_VOICE_ID
        )
        self._stability = (
            stability if stability != 0.5 else prefs.get("stability", 0.5)
        )
        self._similarity_boost = (
            similarity_boost
            if similarity_boost != 0.75
            else prefs.get("similarity_boost", 0.75)
        )
        self._style = style if style != 0.0 else prefs.get("style", 0.0)
        self._speed = speed if speed != 1.0 else prefs.get("speed", 1.0)
        self._cached_voices: Optional[List[str]] = None

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        if not self._api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")

        target_voice = voice_id or self._default_voice_id
        effective_speed = speed if speed != 1.0 else self._speed

        audio = _elevenlabs_synthesize(
            api_key=self._api_key,
            text=text,
            voice_id=target_voice,
            model_id=self._model_id,
            output_format=output_format,
            stability=self._stability,
            similarity_boost=self._similarity_boost,
        )

        return TTSResult(
            audio=audio,
            format=output_format,
            voice_id=target_voice,
            sample_rate=44100 if output_format == "mp3" else 24000,
            metadata={
                "backend": self.backend_id,
                "model_id": self._model_id,
            },
        )

    def available_voices(self) -> List[str]:
        """Return list of voice IDs or fallback presets."""
        if not self._api_key:
            return [
                self._default_voice_id,
                "21m00Tcm4TlvDq8ikWAM",
                "AZnzlk1XvdvUeBnXmlld",
            ]

        if self._cached_voices is not None:
            return self._cached_voices

        try:
            voices = _fetch_voices(self._api_key)
            self._cached_voices = [v["voice_id"] for v in voices]
            return self._cached_voices
        except Exception as exc:
            logger.warning("Failed to fetch ElevenLabs voices: %s", exc)
            return [self._default_voice_id]

    def health(self) -> bool:
        """Check if backend has credentials configured."""
        return bool(self._api_key)
