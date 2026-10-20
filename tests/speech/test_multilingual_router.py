"""Comprehensive tests for Ultron Multilingual TTS Router and Single-Identity Invariance.

Verifies:
1. Truthful capability registry metadata (licensing, hardware, model sizes, languages).
2. Honest language coverage (Windows SAPI only supports English; Chatterbox does not support Urdu).
3. Directive and script language detection (Urdu, Hindi, English).
4. Truthful voice resolution and honest error reporting without silent wrong-language fallback.
5. Invariance of canonical Electron hologram under voice gender changes.
6. API routes: /v1/speech/capabilities, /v1/speech/resolve, /v1/speech/preview.
7. Free-first operation and zero silent paid provider billing.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openjarvis.core.user_preferences import (
    DEFAULT_PRESENTATION,
    get_personalization_preferences,
    set_personalization_preferences,
)
from openjarvis.server.app import create_app
from openjarvis.speech.router import (
    EngineCapability,
    VoiceMetadata,
    build_capabilities_registry,
    detect_language,
    tts_router,
)


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_capabilities_registry_truthfulness():
    """Verify truthful metadata, licensing, and language capabilities."""
    registry = build_capabilities_registry()

    # 1. Windows SAPI
    sapi = registry["system"]
    assert sapi.is_local is True
    assert sapi.is_free is True
    assert sapi.requires_key is False
    assert sapi.supported_languages == ["en"]
    assert any(v.id == "david" and v.gender == "masculine" for v in sapi.voices)
    assert any(v.id == "zira" and v.gender == "feminine" for v in sapi.voices)

    # 2. Piper ONNX
    piper = registry["piper"]
    assert piper.is_local is True
    assert piper.is_free is True
    assert piper.requires_key is False
    assert "en" in piper.supported_languages
    assert "hi" in piper.supported_languages
    assert "ur" in piper.supported_languages

    # 3. Chatterbox Multilingual V3
    chatterbox = registry["chatterbox"]
    assert chatterbox.status == "evaluated_not_recommended"
    assert "ur" not in chatterbox.supported_languages  # Truthful: Chatterbox does NOT support Urdu
    assert "en" in chatterbox.supported_languages
    assert "hi" in chatterbox.supported_languages
    assert "Non-Commercial" in chatterbox.license

    # 4. Urdu VITS
    urdu_vits = registry["urdu_vits"]
    assert urdu_vits.status == "experimental"
    assert urdu_vits.supported_languages == ["ur"]

    # 5. Paid cloud providers
    el = registry["elevenlabs"]
    assert el.is_free is False
    assert el.requires_key is True
    assert "Paid cloud API" in el.cost_notice

    openai_tts = registry["openai_tts"]
    assert openai_tts.is_free is False
    assert openai_tts.requires_key is True
    assert "Billed per character" in openai_tts.cost_notice


def test_detect_language_directives():
    """Verify accurate extraction of language directives and scripts."""
    # Urdu
    assert detect_language("Jarvis, مجھے اردو میں جواب دو.") == "ur"
    assert detect_language("Please reply in urdu") == "ur"
    assert detect_language("yeh sawal urdu mein batao") == "ur"
    assert detect_language("السلام علیکم آپ کیسے ہیں؟") == "ur"

    # Hindi
    assert detect_language("Jarvis, हिंदी में جواب دو.") == "hi"
    assert detect_language("Jarvis, answer in hindi please") == "hi"
    assert detect_language("yeh hindi mein samjhao") == "hi"
    assert detect_language("नमस्ते, आप कैसे हैं?") == "hi"

    # English
    assert detect_language("Jarvis, answer me in English.") == "en"
    assert detect_language("Please speak in english.") == "en"
    assert detect_language("Explain how quantum superposition works.") == "en"

    # Default fallback
    assert detect_language("12345 !@#$", default_language="en") == "en"


def test_resolve_engine_and_voice():
    """Verify voice resolution and honest reporting of unsupported combinations."""
    # 1. Native Windows SAPI (English masculine -> David)
    res_david = tts_router.resolve_engine_and_voice(
        language="en",
        voice_gender="masculine",
        preferred_provider="system",
    )
    assert res_david["status"] == "supported"
    assert res_david["engine_id"] == "system"
    assert res_david["voice_id"] == "david"
    assert res_david["is_local"] is True

    # 2. Native Windows SAPI (English feminine -> Zira)
    res_zira = tts_router.resolve_engine_and_voice(
        language="en",
        voice_gender="feminine",
        preferred_provider="system",
    )
    assert res_zira["status"] == "supported"
    assert res_zira["engine_id"] == "system"
    assert res_zira["voice_id"] == "zira"
    assert res_zira["is_local"] is True

    # 3. Native Windows SAPI + Urdu -> Honest unsupported status
    res_ur = tts_router.resolve_engine_and_voice(
        language="ur",
        voice_gender="masculine",
        preferred_provider="system",
    )
    assert res_ur["status"] == "unsupported_by_engine"
    assert res_ur["engine_id"] == "system"
    assert "does not support 'ur'" in res_ur["message"]

    # 4. Native Windows SAPI + Hindi -> Honest unsupported status
    res_hi = tts_router.resolve_engine_and_voice(
        language="hi",
        voice_gender="masculine",
        preferred_provider="system",
    )
    assert res_hi["status"] == "unsupported_by_engine"
    assert res_hi["engine_id"] == "system"
    assert "does not support 'hi'" in res_hi["message"]


def test_detect_and_resolve():
    """Verify turn-level directive detection paired with voice resolution."""
    res_turn_ur = tts_router.detect_and_resolve(
        text="Jarvis, مجھے اردو میں جواب دو.",
        default_language="en",
        preferred_provider="system",
    )
    assert res_turn_ur["detected_language"] == "ur"
    assert res_turn_ur["status"] == "unsupported_by_engine"

    res_turn_en = tts_router.detect_and_resolve(
        text="Jarvis, answer me in English.",
        default_language="ur",
        voice_gender="masculine",
        preferred_provider="system",
    )
    assert res_turn_en["detected_language"] == "en"
    assert res_turn_en["status"] == "supported"
    assert res_turn_en["voice_id"] == "david"


def test_single_hologram_identity_invariance():
    """Verify that changing voice preferences never alters the canonical Electron hologram."""
    # Update voice gender to masculine
    res1 = set_personalization_preferences({"voice_gender": "masculine"})
    assert res1["voice_gender"] == "masculine"
    assert res1["presentation"] == DEFAULT_PRESENTATION  # "neutral"

    # Update voice gender to feminine
    res2 = set_personalization_preferences({"voice_gender": "feminine"})
    assert res2["voice_gender"] == "feminine"
    assert res2["presentation"] == DEFAULT_PRESENTATION  # "neutral"

    # Legacy presentation key safely maps without changing canonical Electron hologram
    res3 = set_personalization_preferences({"presentation": "masculine"})
    assert res3["voice_gender"] == "masculine"
    assert res3["presentation"] == DEFAULT_PRESENTATION  # "neutral"


def test_api_capabilities_endpoint(client):
    """Verify GET /v1/speech/capabilities exposes the capability registry."""
    resp = client.get("/v1/speech/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data
    caps = data["capabilities"]
    assert "system" in caps
    assert "piper" in caps
    assert "chatterbox" in caps
    assert "elevenlabs" in caps
    assert caps["system"]["supported_languages"] == ["en"]
    assert caps["chatterbox"]["status"] == "evaluated_not_recommended"


def test_api_resolve_endpoint(client):
    """Verify POST /v1/speech/resolve accurately resolves voice and detects directives."""
    resp = client.post(
        "/v1/speech/resolve",
        json={
            "text": "Jarvis, mujhe urdu mein jawab do",
            "provider": "system",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected_language"] == "ur"
    assert data["status"] == "unsupported_by_engine"

    resp_en = client.post(
        "/v1/speech/resolve",
        json={
            "language": "en",
            "voice_gender": "feminine",
            "provider": "system",
        },
    )
    assert resp_en.status_code == 200
    data_en = resp_en.json()
    assert data_en["status"] == "supported"
    assert data_en["voice_id"] == "zira"


def test_api_preview_windows_sapi(client):
    """Verify POST /v1/speech/preview generates genuine WAV audio for English SAPI."""
    resp = client.post(
        "/v1/speech/preview",
        json={
            "provider": "system",
            "language": "en",
            "voice_gender": "masculine",
            "text": "Ultron speech synthesis online.",
        },
    )
    assert resp.status_code == 200
    # On Windows, synthesize_wav produces real audio/wav; verify provider header
    if resp.headers.get("content-type") == "audio/wav":
        assert resp.headers["X-Voice-Provider"] == "windows_sapi"
        assert resp.headers["X-Voice-Gender"] == "masculine"
        assert len(resp.content) > 1000
    else:
        # If running in environment without cscript/SAPI
        assert resp.json()["status"] == "client_synthesis"


def test_api_preview_unsupported_language_honesty(client):
    """Verify POST /v1/speech/preview does not fake support for Urdu in Windows SAPI."""
    resp = client.post(
        "/v1/speech/preview",
        json={
            "provider": "system",
            "language": "ur",
            "text": "السلام علیکم",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unsupported_by_engine"
    assert "does not support 'ur'" in data["message"]


def test_api_preview_elevenlabs_unauthorized_when_no_key(client):
    """Verify ElevenLabs preview is rejected with 401 if no API key is provided."""
    with patch("openjarvis.core.user_preferences.get_elevenlabs_api_key", return_value=""):
        resp = client.post(
            "/v1/speech/preview",
            json={
                "provider": "elevenlabs",
                "voice_id": "test_id",
                "text": "Hello world",
            },
        )
        assert resp.status_code == 401
        assert "not configured" in resp.json()["detail"]
