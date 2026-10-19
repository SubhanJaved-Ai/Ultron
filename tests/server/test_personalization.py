"""Tests for personalization preferences and API routes."""

import pytest
from fastapi.testclient import TestClient

from openjarvis.core.user_preferences import (
    VALID_LANGUAGES,
    VALID_PERSONAS,
    VALID_PRESENTATIONS,
    get_personalization_preferences,
    set_personalization_preferences,
)
from openjarvis.server.app import create_app


@pytest.fixture(autouse=True)
def _clean_personalization_env(monkeypatch, tmp_path):
    """Ensure tests run against a temporary config path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openjarvis.core.user_preferences.USER_PREFERENCES_PATH",
        config_dir / "user_preferences.json",
    )


def test_personalization_defaults():
    prefs = get_personalization_preferences()
    assert prefs["user_name"] == "Sir"
    assert prefs["presentation"] == "neutral"
    assert prefs["persona"] == "jarvis"
    assert prefs["language"] == "en"
    assert prefs["sound_enabled"] is True
    assert prefs["sound_volume"] == 0.6
    assert prefs["onboarding_completed"] is False


def test_personalization_updates_and_sync():
    updated = set_personalization_preferences(
        {
            "user_name": "Tony Stark",
            "phone_number": "+14155552671",
            "presentation": "masculine",
            "persona": "bro",
            "language": "en",
            "sound_enabled": False,
            "sound_volume": 0.8,
            "onboarding_completed": True,
        }
    )
    assert updated["user_name"] == "Tony Stark"
    assert updated["phone_number"] == "+14155552671"
    assert updated["presentation"] == "masculine"
    assert updated["persona"] == "bro"
    assert updated["sound_enabled"] is False
    assert updated["sound_volume"] == 0.8
    assert updated["onboarding_completed"] is True


def test_personalization_invalid_persona_rejected():
    with pytest.raises(ValueError, match="Invalid persona"):
        set_personalization_preferences({"persona": "non_existent_persona"})


def test_personalization_invalid_presentation_rejected():
    with pytest.raises(ValueError, match="Invalid presentation"):
        set_personalization_preferences({"presentation": "alien"})


def test_personalization_invalid_language_rejected():
    with pytest.raises(ValueError, match="Invalid language"):
        set_personalization_preferences({"language": "klingon"})


def test_personalization_invalid_phone_rejected():
    with pytest.raises(ValueError, match="Invalid phone number"):
        set_personalization_preferences({"phone_number": "abc12345"})


def test_personalization_api_routes():
    app = create_app()
    client = TestClient(app)

    # GET /v1/personalization
    resp = client.get("/v1/personalization")
    assert resp.status_code == 200
    data = resp.json()
    assert data["persona"] == "jarvis"
    assert data["presentation"] == "neutral"

    # POST /v1/personalization valid
    post_resp = client.post(
        "/v1/personalization",
        json={
            "user_name": "Pepper Potts",
            "presentation": "feminine",
            "persona": "mentor",
            "language": "ur",
            "sound_enabled": True,
            "onboarding_completed": True,
        },
    )
    assert post_resp.status_code == 200
    updated_data = post_resp.json()
    assert updated_data["user_name"] == "Pepper Potts"
    assert updated_data["presentation"] == "feminine"
    assert updated_data["persona"] == "mentor"
    assert updated_data["language"] == "ur"

    # POST /v1/personalization invalid persona -> 422
    err_resp = client.post(
        "/v1/personalization",
        json={"persona": "invalid_one"},
    )
    assert err_resp.status_code == 422


def test_voice_settings_api_capabilities():
    app = create_app()
    client = TestClient(app)

    resp = client.get("/v1/speech/voice-settings")
    assert resp.status_code == 200
    data = resp.json()

    assert "available_providers" in data
    assert "personalization" in data
    providers = {p["id"]: p for p in data["available_providers"]}

    # SAPI / System is free and English-only
    assert "system" in providers
    assert providers["system"]["free"] is True
    assert "en" in providers["system"]["supported_languages"]

    # ElevenLabs is paid, key required, supports en and ur
    assert "elevenlabs" in providers
    assert providers["elevenlabs"]["free"] is False
    assert providers["elevenlabs"]["requires_key"] is True
    assert "ur" in providers["elevenlabs"]["supported_languages"]


def test_voice_preview_fallback():
    app = create_app()
    client = TestClient(app)

    # When no local model or ElevenLabs key is configured, /v1/speech/preview returns client synthesis descriptor
    resp = client.post(
        "/v1/speech/preview",
        json={
            "provider": "system",
            "voice_id": "default",
            "language": "en",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "client_synthesis"
    assert "Greetings, I am Ultron" in data["text"]
