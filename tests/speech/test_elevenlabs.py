"""Tests for ElevenLabs TTS backend."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech._tts_discovery import get_tts_backend
from openjarvis.speech.elevenlabs_tts import (
    DEFAULT_ELEVENLABS_MODEL,
    DEFAULT_ELEVENLABS_VOICE_ID,
    ElevenLabsTTSBackend,
)


def test_elevenlabs_registered():
    """Verify elevenlabs backend is in TTSRegistry."""
    from openjarvis.speech.elevenlabs_tts import ensure_registered

    ensure_registered()
    assert TTSRegistry.contains("elevenlabs")
    cls = TTSRegistry.get("elevenlabs")
    assert cls is ElevenLabsTTSBackend


def test_elevenlabs_health():
    """Verify health reflects API key configuration."""
    backend_no_key = ElevenLabsTTSBackend(api_key="")
    assert backend_no_key.health() is False

    backend_with_key = ElevenLabsTTSBackend(api_key="el-test-key-123")
    assert backend_with_key.health() is True


def test_elevenlabs_missing_key_raises():
    """Verify synthesize raises RuntimeError when no API key is provided."""
    backend = ElevenLabsTTSBackend(api_key="")
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY not set"):
        backend.synthesize("Hello Jarvis")


def test_elevenlabs_synthesize_success():
    """Verify synthesize returns correct TTSResult with mock audio."""
    backend = ElevenLabsTTSBackend(api_key="el-test-key-123")

    with patch(
        "openjarvis.speech.elevenlabs_tts._elevenlabs_synthesize",
        return_value=b"mock-elevenlabs-audio-bytes",
    ) as mock_req:
        result = backend.synthesize("Welcome home, sir.")

        assert result.audio == b"mock-elevenlabs-audio-bytes"
        assert result.format == "mp3"
        assert result.voice_id == DEFAULT_ELEVENLABS_VOICE_ID
        assert result.metadata["backend"] == "elevenlabs"
        assert result.metadata["model_id"] == DEFAULT_ELEVENLABS_MODEL

        mock_req.assert_called_once_with(
            api_key="el-test-key-123",
            text="Welcome home, sir.",
            voice_id=DEFAULT_ELEVENLABS_VOICE_ID,
            model_id=DEFAULT_ELEVENLABS_MODEL,
            output_format="mp3",
            stability=0.5,
            similarity_boost=0.75,
        )


def test_elevenlabs_custom_voice_and_format():
    """Verify custom voice ID and parameters pass through."""
    backend = ElevenLabsTTSBackend(
        api_key="el-test-key-123",
        model_id="eleven_multilingual_v2",
        stability=0.7,
        similarity_boost=0.85,
    )

    with patch(
        "openjarvis.speech.elevenlabs_tts._elevenlabs_synthesize",
        return_value=b"mock-pcm-audio",
    ) as mock_req:
        result = backend.synthesize(
            "Systems online.",
            voice_id="custom-jarvis-voice",
            output_format="pcm",
        )

        assert result.audio == b"mock-pcm-audio"
        assert result.format == "pcm"
        assert result.voice_id == "custom-jarvis-voice"
        assert result.metadata["model_id"] == "eleven_multilingual_v2"

        mock_req.assert_called_once_with(
            api_key="el-test-key-123",
            text="Systems online.",
            voice_id="custom-jarvis-voice",
            model_id="eleven_multilingual_v2",
            output_format="pcm",
            stability=0.7,
            similarity_boost=0.85,
        )


def test_elevenlabs_available_voices_fetching():
    """Verify available_voices fetches and caches remote voices."""
    backend = ElevenLabsTTSBackend(api_key="el-test-key-123")

    mock_voices = [
        {"voice_id": "v1", "name": "Jarvis Classic"},
        {"voice_id": "v2", "name": "Jarvis Alt"},
    ]

    with patch(
        "openjarvis.speech.elevenlabs_tts._fetch_voices",
        return_value=mock_voices,
    ) as mock_fetch:
        voices = backend.available_voices()
        assert voices == ["v1", "v2"]
        mock_fetch.assert_called_once()

        # Second call should use cache
        cached_voices = backend.available_voices()
        assert cached_voices == ["v1", "v2"]
        assert mock_fetch.call_count == 1


def test_elevenlabs_discovery_with_key():
    """Verify get_tts_backend picks elevenlabs when preferred."""
    with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test-key"}):
        backend = get_tts_backend("elevenlabs")
        assert backend is not None
        assert backend.backend_id == "elevenlabs"
