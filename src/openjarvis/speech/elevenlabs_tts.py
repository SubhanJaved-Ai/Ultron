"""ElevenLabs text-to-speech backend.

Uses the ElevenLabs REST API for lifelike, cinematic voice synthesis.
Requires ELEVENLABS_API_KEY environment variable, config, or vault.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

logger = logging.getLogger(__name__)

_ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_ELEVENLABS_MODEL = "eleven_turbo_v2_5"
# Classic British voice ("George" / "Adam" / "Jarvis" preset)
DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"


def _elevenlabs_synthesize(
    api_key: str,
    text: str,
    voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID,
    model_id: str = DEFAULT_ELEVENLABS_MODEL,
    output_format: str = "mp3",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    timeout: float = 60.0,
) -> bytes:
    """Call the ElevenLabs TTS API and return raw audio bytes."""
    format_param = "mp3_44100_128" if output_format == "mp3" else "pcm_24000"
    url = (
        f"{_ELEVENLABS_API_BASE}/text-to-speech/{voice_id}?output_format={format_param}"
    )

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "use_speaker_boost": True,
        },
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _fetch_voices(api_key: str, timeout: float = 10.0) -> List[Dict[str, str]]:
    """Fetch list of available voices from ElevenLabs."""
    url = f"{_ELEVENLABS_API_BASE}/voices"
    headers = {"xi-api-key": api_key}
    resp = httpx.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    voices = data.get("voices", [])
    return [
        {"voice_id": v.get("voice_id", ""), "name": v.get("name", "")}
        for v in voices
        if v.get("voice_id")
    ]


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
        model_id: str = DEFAULT_ELEVENLABS_MODEL,
        default_voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> None:
        self._api_key = (
            api_key
            or os.environ.get("ELEVENLABS_API_KEY", "")
            or os.environ.get("ELEVEN_API_KEY", "")
        )
        self._model_id = model_id
        self._default_voice_id = default_voice_id
        self._stability = stability
        self._similarity_boost = similarity_boost
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
