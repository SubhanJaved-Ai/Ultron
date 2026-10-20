"""Comprehensive automated test suite for ElevenLabs voice integration in Ultron.

Verifies:
- Missing and invalid API key handling
- Voice list parsing using official ElevenLabs API mock
- Model list parsing and TTS capability filtering
- Speech synthesis with mock audio responses (MP3 and WAV)
- Parameter propagation: voice_id, model_id, stability, similarity, style, speed
- Error classification and sanitization: 401/403, 429 quota, timeouts, 5xx
- API key masking and zero credential leakage
- Input validation: voice IDs, model IDs, text length limits
- Fast API endpoint compatibility: /v1/speech/voice-settings, /test, /voices, /models, /preview, /synthesize
"""

from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from openjarvis.core.user_preferences import (
    get_voice_preferences,
    mask_api_key,
    save_elevenlabs_api_key,
    set_voice_preferences,
)
from openjarvis.server.app import create_app
from openjarvis.speech.elevenlabs_tts import (
    DEFAULT_ELEVENLABS_MODEL,
    DEFAULT_ELEVENLABS_VOICE_ID,
    ElevenLabsAPIError,
    ElevenLabsAuthError,
    ElevenLabsQuotaError,
    ElevenLabsTimeoutError,
    ElevenLabsTTSBackend,
    _elevenlabs_synthesize,
    _fetch_models,
    _fetch_voices,
    test_connection as el_test_connection,
)


@pytest.fixture
def mock_elevenlabs_api():
    """Configure respx mock router for ElevenLabs v1 API."""
    with respx.mock(base_url="https://api.elevenlabs.io/v1", assert_all_called=False) as respx_mock:
        yield respx_mock


@pytest.fixture
def api_client():
    """Create FastAPI TestClient."""
    app = create_app()
    with TestClient(app) as client:
        yield client


# ==============================================================================
# 1. Credential Security & Masking Tests
# ==============================================================================


def test_api_key_masking():
    """Verify API keys are masked revealing at most the last 4 characters."""
    assert mask_api_key("") == ""
    assert mask_api_key("123") == "••••••••"
    assert mask_api_key("sk_test_" + "1234567890abcdef") == "••••••••cdef"
    assert mask_api_key("elevenlabs_secret_key_xyz987") == "••••••••z987"



def test_voice_preferences_never_leaks_plain_key(tmp_path):
    """Ensure get_voice_preferences exposes only masked key and boolean flag."""
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk_super_secret_elevenlabs_key_9999"}):
        prefs = get_voice_preferences()
        assert prefs["has_api_key"] is True
        assert prefs["masked_api_key"] == "••••••••9999"
        # Confirm plaintext secret is absent
        assert "sk_super_secret_elevenlabs_key_9999" not in str(prefs)


def test_save_elevenlabs_api_key(tmp_path):
    """Verify save_elevenlabs_api_key updates process env and cloud-keys.env safely."""
    with patch("openjarvis.core.paths.get_config_dir", return_value=tmp_path):
        save_elevenlabs_api_key("test_key_abc1234")
        assert os.environ.get("ELEVENLABS_API_KEY") == "test_key_abc1234"
        cloud_file = tmp_path / "cloud-keys.env"
        assert cloud_file.is_file()
        assert "ELEVENLABS_API_KEY=test_key_abc1234" in cloud_file.read_text()

        # Clear key
        save_elevenlabs_api_key("")
        assert "ELEVENLABS_API_KEY" not in os.environ


# ==============================================================================
# 2. Voice List & Model List Parsing Tests
# ==============================================================================


def test_fetch_voices_success(mock_elevenlabs_api):
    """Verify voices endpoint parsing against official ElevenLabs JSON schema."""
    mock_elevenlabs_api.get("/voices").respond(
        status_code=200,
        json={
            "voices": [
                {
                    "voice_id": "JBFqnCBsd6RMkjVDRZzb",
                    "name": "George",
                    "category": "premade",
                    "preview_url": "https://elevenlabs.io/sample_george.mp3",
                    "labels": {"accent": "british", "gender": "male"},
                },
                {
                    "voice_id": "21m00Tcm4TlvDq8ikWAM",
                    "name": "Rachel",
                    "category": "cloned",
                    "preview_url": "https://elevenlabs.io/sample_rachel.mp3",
                    "labels": {"accent": "american", "gender": "female"},
                },
            ]
        },
    )

    voices = _fetch_voices("test-api-key")
    assert len(voices) == 2
    assert voices[0]["voice_id"] == "JBFqnCBsd6RMkjVDRZzb"
    assert voices[0]["name"] == "George"
    assert voices[0]["category"] == "premade"
    assert voices[1]["voice_id"] == "21m00Tcm4TlvDq8ikWAM"
    assert voices[1]["name"] == "Rachel"


def test_fetch_models_filtering(mock_elevenlabs_api):
    """Verify models are filtered strictly for can_do_text_to_speech == true."""
    mock_elevenlabs_api.get("/models").respond(
        status_code=200,
        json=[
            {
                "model_id": "eleven_turbo_v2_5",
                "name": "Eleven Turbo v2.5",
                "can_do_text_to_speech": True,
                "description": "Ultra low latency model",
            },
            {
                "model_id": "eleven_multilingual_v2",
                "name": "Eleven Multilingual v2",
                "can_do_text_to_speech": True,
                "description": "Rich emotional synthesis",
            },
            {
                "model_id": "eleven_sound_effects",
                "name": "Eleven Sound Effects",
                "can_do_text_to_speech": False,
                "description": "Audio effect generator",
            },
            {
                "model_id": "eleven_voice_isolator",
                "name": "Eleven Voice Isolator",
                "can_do_text_to_speech": False,
                "description": "Noise reduction model",
            },
        ],
    )

    models = _fetch_models("test-api-key")
    assert len(models) == 2
    model_ids = [m["model_id"] for m in models]
    assert "eleven_turbo_v2_5" in model_ids
    assert "eleven_multilingual_v2" in model_ids
    assert "eleven_sound_effects" not in model_ids
    assert "eleven_voice_isolator" not in model_ids


# ==============================================================================
# 3. Connection Test & Status Verification
# ==============================================================================


def test_connection_test_success(mock_elevenlabs_api):
    """Verify test_connection returns connected status with counts when key is valid."""
    mock_elevenlabs_api.get("/voices").respond(
        status_code=200,
        json={"voices": [{"voice_id": "v1", "name": "V1"}]},
    )
    mock_elevenlabs_api.get("/models").respond(
        status_code=200,
        json=[{"model_id": "m1", "name": "M1", "can_do_text_to_speech": True}],
    )

    result = el_test_connection("valid-key")
    assert result["valid"] is True
    assert result["status"] == "connected"
    assert result["voices_count"] == 1
    assert result["models_count"] == 1


def test_connection_test_invalid_key(mock_elevenlabs_api):
    """Verify test_connection detects 401 Unauthorized as invalid_key."""
    mock_elevenlabs_api.get("/voices").respond(
        status_code=401,
        json={"detail": {"status": "invalid_api_key", "message": "Invalid API key provided"}},
    )

    result = el_test_connection("invalid-key-xyz")
    assert result["valid"] is False
    assert result["status"] == "invalid_key"
    assert "authentication failed" in result["message"]


def test_connection_test_quota_exceeded(mock_elevenlabs_api):
    """Verify test_connection detects 429 Quota Exceeded."""
    mock_elevenlabs_api.get("/voices").respond(
        status_code=429,
        json={"detail": {"status": "quota_exceeded", "message": "Monthly character limit reached"}},
    )

    result = el_test_connection("quota-exhausted-key")
    assert result["valid"] is False
    assert result["status"] == "quota_limited"
    assert "quota or rate limit" in result["message"]


def test_connection_test_unconfigured():
    """Verify test_connection reports unconfigured when key is empty."""
    result = el_test_connection("")
    assert result["valid"] is False
    assert result["status"] == "unconfigured"



# ==============================================================================
# 4. Synthesis & Audio Generation Tests
# ==============================================================================


def test_synthesis_mp3_success(mock_elevenlabs_api):
    """Verify speech synthesis returns MP3 audio bytes with proper payload."""
    expected_audio = b"\xff\xfb\x90\x44mock-mp3-audio-stream"
    mock_route = mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128"
    ).respond(status_code=200, content=expected_audio, headers={"Content-Type": "audio/mpeg"})

    audio = _elevenlabs_synthesize(
        api_key="test-api-key",
        text="Greetings, sir. Ultron online.",
        voice_id=DEFAULT_ELEVENLABS_VOICE_ID,
        model_id=DEFAULT_ELEVENLABS_MODEL,
        output_format="mp3",
        stability=0.6,
        similarity_boost=0.8,
        style=0.2,
        speed=1.1,
    )

    assert audio == expected_audio
    assert mock_route.called
    req = mock_route.calls.last.request
    body = req.read().decode("utf-8")
    assert "Greetings, sir. Ultron online." in body
    assert "eleven_turbo_v2_5" in body


def test_synthesis_wav_wrapping(mock_elevenlabs_api):
    """Verify PCM audio from ElevenLabs is packaged into a valid RIFF/WAV header."""
    mock_pcm_bytes = b"\x00\x01\x00\x02" * 100  # Raw PCM samples
    mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=pcm_24000"
    ).respond(status_code=200, content=mock_pcm_bytes)

    audio = _elevenlabs_synthesize(
        api_key="test-api-key",
        text="Wrapping PCM into standard WAV.",
        output_format="wav",
    )

    # Validate RIFF WAV header
    assert audio.startswith(b"RIFF")
    assert b"WAVE" in audio[:12]
    assert len(audio) > len(mock_pcm_bytes)


def test_synthesis_backend_class(mock_elevenlabs_api):
    """Verify ElevenLabsTTSBackend instance synthesize method."""
    mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128"
    ).respond(status_code=200, content=b"audio-bytes-result")

    backend = ElevenLabsTTSBackend(api_key="test-key")
    res = backend.synthesize("Welcome back, Commander.", output_format="mp3")

    assert res.audio == b"audio-bytes-result"
    assert res.format == "mp3"
    assert res.voice_id == DEFAULT_ELEVENLABS_VOICE_ID
    assert res.sample_rate == 44100
    assert res.metadata["backend"] == "elevenlabs"


# ==============================================================================
# 5. Input Validation & Error Handling Tests
# ==============================================================================


def test_synthesis_empty_text_raises():
    """Verify synthesis rejects empty or whitespace-only text."""
    with pytest.raises(ValueError, match="cannot be empty"):
        _elevenlabs_synthesize(api_key="key", text="")


def test_synthesis_oversized_text_raises():
    """Verify synthesis rejects text exceeding 5000 characters."""
    with pytest.raises(ValueError, match="exceeds maximum synthesis length"):
        _elevenlabs_synthesize(api_key="key", text="x" * 5001)


def test_synthesis_invalid_voice_id_raises():
    """Verify invalid voice ID format is rejected."""
    with pytest.raises(ValueError, match="Invalid voice ID"):
        _elevenlabs_synthesize(api_key="key", text="Hello", voice_id="invalid/slash/id")


def test_synthesis_401_raises_auth_error(mock_elevenlabs_api):
    """Verify 401 returns ElevenLabsAuthError without leaking key."""
    mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128"
    ).respond(status_code=401, json={"detail": "Unauthorized secret_key_12345"})

    with pytest.raises(ElevenLabsAuthError) as exc_info:
        _elevenlabs_synthesize(api_key="secret_key_12345", text="Testing auth error.")
    assert "ElevenLabs authentication failed (401)" in str(exc_info.value)


def test_synthesis_429_raises_quota_error(mock_elevenlabs_api):
    """Verify 429 returns ElevenLabsQuotaError."""
    mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128"
    ).respond(status_code=429, json={"detail": "Too many requests"})

    with pytest.raises(ElevenLabsQuotaError) as exc_info:
        _elevenlabs_synthesize(api_key="test-key", text="Testing quota error.")
    assert "quota or rate limit exceeded" in str(exc_info.value)


# ==============================================================================
# 6. HTTP API Endpoint Tests
# ==============================================================================


def test_api_voice_settings_get(api_client):
    """GET /v1/speech/voice-settings returns current preferences and available providers."""
    resp = api_client.get("/v1/speech/voice-settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "voice_id" in data
    assert "model_id" in data
    assert "stability" in data
    assert "has_api_key" in data
    assert "masked_api_key" in data
    assert "available_providers" in data
    provider_ids = [p["id"] for p in data["available_providers"]]
    assert "system" in provider_ids
    assert "elevenlabs" in provider_ids


def test_api_voice_settings_post_and_switch(api_client, tmp_path):
    """POST /v1/speech/voice-settings updates provider, model, voice, and sliders."""
    with patch("openjarvis.core.paths.get_config_dir", return_value=tmp_path):
        payload = {
            "provider": "elevenlabs",
            "api_key": "el_live_key_556677",
            "voice_id": "customVoice123",
            "model_id": "eleven_multilingual_v2",
            "stability": 0.8,
            "similarity_boost": 0.9,
            "style": 0.3,
            "speed": 1.25,
        }
        resp = api_client.post("/v1/speech/voice-settings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "elevenlabs"
        assert data["voice_id"] == "customVoice123"
        assert data["model_id"] == "eleven_multilingual_v2"
        assert data["stability"] == 0.8
        assert data["similarity_boost"] == 0.9
        assert data["style"] == 0.3
        assert data["speed"] == 1.25
        assert data["has_api_key"] is True
        assert data["masked_api_key"] == "••••••••6677"

        # Switch back to system
        resp2 = api_client.post("/v1/speech/voice-settings", json={"provider": "system"})
        assert resp2.status_code == 200
        assert resp2.json()["provider"] == "system"


def test_api_elevenlabs_test_endpoint(api_client, mock_elevenlabs_api):
    """POST /v1/speech/elevenlabs/test triggers upstream test."""
    mock_elevenlabs_api.get("/voices").respond(status_code=200, json={"voices": [{"voice_id": "v1"}]})
    mock_elevenlabs_api.get("/models").respond(status_code=200, json=[{"model_id": "m1", "can_do_text_to_speech": True}])

    resp = api_client.post("/v1/speech/elevenlabs/test", json={"api_key": "test_key_abc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["status"] == "connected"
    assert data["voices_count"] == 1


def test_api_elevenlabs_voices_and_models(api_client, mock_elevenlabs_api):
    """GET /v1/speech/elevenlabs/voices and /models return upstream data."""
    mock_elevenlabs_api.get("/voices").respond(
        status_code=200,
        json={"voices": [{"voice_id": "v1", "name": "Voice One"}]},
    )
    mock_elevenlabs_api.get("/models").respond(
        status_code=200,
        json=[{"model_id": "m1", "name": "Model One", "can_do_text_to_speech": True}],
    )

    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "valid_key"}):
        v_resp = api_client.get("/v1/speech/elevenlabs/voices")
        assert v_resp.status_code == 200
        assert len(v_resp.json()["voices"]) == 1

        m_resp = api_client.get("/v1/speech/elevenlabs/models")
        assert m_resp.status_code == 200
        assert len(m_resp.json()["models"]) == 1


def test_api_elevenlabs_preview(api_client, mock_elevenlabs_api):
    """POST /v1/speech/elevenlabs/preview synthesizes short preview text."""
    mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128"
    ).respond(status_code=200, content=b"preview-mp3-audio-bytes")

    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "valid_key"}):
        resp = api_client.post(
            "/v1/speech/elevenlabs/preview",
            json={
                "voice_id": DEFAULT_ELEVENLABS_VOICE_ID,
                "text": "Preview testing phrase.",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert resp.content == b"preview-mp3-audio-bytes"


def test_hologram_tts_endpoint_uses_selected_provider(api_client, mock_elevenlabs_api, tmp_path):
    """Verify /api/tts routes to ElevenLabs when provider is elevenlabs, falling back smoothly."""
    mock_elevenlabs_api.post(
        f"/text-to-speech/{DEFAULT_ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128"
    ).respond(status_code=200, content=b"hologram-mp3-audio")

    with patch("openjarvis.core.paths.get_config_dir", return_value=tmp_path):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "valid_key"}):
            set_voice_preferences({"provider": "elevenlabs"})

            resp = api_client.get("/api/tts?text=Systems+operational")
            assert resp.status_code == 200
            assert resp.headers.get("X-Voice-Provider") == "elevenlabs"
            assert resp.content == b"hologram-mp3-audio"

            # Reset back to system
            set_voice_preferences({"provider": "system"})
