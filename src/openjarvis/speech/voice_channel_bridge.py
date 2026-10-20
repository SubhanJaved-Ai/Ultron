"""VoiceChannelBridge — bidirectional audio processing for messaging channels.

Provides audio transcription (STT) for incoming voice memos and voice
synthesis (TTS) for outgoing voice notes on Telegram, WhatsApp, and Web channels.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from openjarvis.speech._discovery import get_speech_backend
from openjarvis.speech._tts_discovery import get_tts_backend

logger = logging.getLogger(__name__)


class VoiceChannelBridge:
    """Bridges messaging channels with speech-to-text and text-to-speech pipelines."""

    def __init__(
        self,
        *,
        preferred_tts: str = "elevenlabs",
        tts_voice_id: str = "",
    ) -> None:
        self.preferred_tts = preferred_tts
        self.tts_voice_id = tts_voice_id

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        suffix: str = ".ogg",
        language: Optional[str] = None,
    ) -> str:
        """Transcribe raw audio bytes into text using the active STT backend.

        Writes bytes temporarily to disk to support backends requiring a file path.
        """
        if not audio_bytes:
            return ""

        # First, try to load configured JarvisConfig and speech backend
        backend = None
        try:
            from openjarvis.core.config import load_config

            config = load_config()
            backend = get_speech_backend(config)
        except Exception as exc:
            logger.debug("Failed to resolve speech backend from config: %s", exc)

        # Fallback: check direct cloud STT via environment (OpenAI or Groq Whisper)
        if backend is None:
            api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if api_key:
                try:
                    from openjarvis.speech.openai_whisper import OpenAIWhisperBackend

                    base_url = (
                        "https://api.groq.com/openai/v1"
                        if os.environ.get("GROQ_API_KEY")
                        else "https://api.openai.com/v1"
                    )
                    backend = OpenAIWhisperBackend(api_key=api_key, base_url=base_url)
                except Exception as exc:
                    logger.debug("Cloud Whisper fallback failed to initialize: %s", exc)

        if backend is None:
            logger.warning("No speech-to-text backend available for transcription")
            return "[Voice note received: STT backend not configured]"

        # Create temporary audio file for transcription
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(audio_bytes)

        try:
            result = backend.transcribe(str(temp_path), language=language)
            return (result.text or "").strip()
        except Exception as exc:
            logger.error("Audio transcription failed: %s", exc)
            return ""
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def synthesize_voice(
        self,
        text: str,
        *,
        voice_id: str = "",
        output_format: str = "mp3",
    ) -> Optional[bytes]:
        """Synthesize text into speech audio bytes using available TTS backend."""
        clean_text = (text or "").strip()
        if not clean_text:
            return None

        # Resolve TTS backend (prefers ElevenLabs, falls back to Kokoro/OpenAI/Cartesia)
        target_voice = voice_id or self.tts_voice_id
        tts_backend = get_tts_backend(preferred=self.preferred_tts)
        if tts_backend is None:
            logger.debug("No TTS backend available for voice synthesis")
            return None

        try:
            result = tts_backend.synthesize(
                clean_text,
                voice_id=target_voice,
                output_format=output_format,
            )
            return result.audio
        except Exception as exc:
            logger.warning(
                "Voice synthesis failed on %s: %s",
                tts_backend.backend_id,
                exc,
            )
            return None


__all__ = ["VoiceChannelBridge"]
