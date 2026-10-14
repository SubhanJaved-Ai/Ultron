"""Unit tests for TSK-P5-02 — Dynamic Personality Controls (Soul Circuit).

Covers:
- Float validation (in-range, boundary, out-of-range, non-finite, non-numeric).
- Persistence round-trip via get_personality / set_personality.
- Unknown key injection rejection.
- Default fallback when no preferences file exists.
- GET  /api/hologram/personality  endpoint.
- POST /api/hologram/personality  endpoint (valid, boundary, out-of-range).
- Prompt composition: each personality extreme produces expected clause.
"""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.app import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["test-model"]
    return engine


def _make_client():
    return TestClient(create_app(_make_engine(), "test-model"))


# ---------------------------------------------------------------------------
# user_preferences.py — unit tests (isolated with tmp_path)
# ---------------------------------------------------------------------------


class TestValidatePersonalityFloat:
    def test_valid_zero(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        assert _validate_personality_float(0.0) == 0.0

    def test_valid_one(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        assert _validate_personality_float(1.0) == 1.0

    def test_valid_midpoint(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        assert _validate_personality_float(0.5) == 0.5

    def test_valid_string_float(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        assert _validate_personality_float("0.75") == 0.75

    def test_boundary_just_above_zero(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        assert _validate_personality_float(0.0001) == 0.0001

    def test_boundary_just_below_one(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        assert _validate_personality_float(0.9999) == 0.9999

    def test_invalid_above_one(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            _validate_personality_float(1.0001)

    def test_invalid_negative(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        with pytest.raises(ValueError):
            _validate_personality_float(-0.1)

    def test_invalid_nan(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        with pytest.raises(ValueError, match="finite"):
            _validate_personality_float(float("nan"))

    def test_invalid_inf(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        with pytest.raises(ValueError, match="finite"):
            _validate_personality_float(math.inf)

    def test_invalid_none(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        with pytest.raises(ValueError):
            _validate_personality_float(None)

    def test_invalid_string_text(self):
        from openjarvis.core.user_preferences import _validate_personality_float
        with pytest.raises(ValueError):
            _validate_personality_float("ignore previous instructions")


class TestGetSetPersonality:
    def test_defaults_when_no_file(self, tmp_path):
        from openjarvis.core import user_preferences
        with patch.object(user_preferences, "_get_pref_file", return_value=tmp_path / "prefs.json"):
            result = user_preferences.get_personality()
        assert result == {"formality": 0.5, "verbosity": 0.5, "warmth": 0.5}

    def test_set_and_get_roundtrip(self, tmp_path):
        from openjarvis.core import user_preferences
        pref_file = tmp_path / "prefs.json"
        with patch.object(user_preferences, "_get_pref_file", return_value=pref_file):
            saved = user_preferences.set_personality({"formality": 0.9, "verbosity": 0.1, "warmth": 0.75})
            loaded = user_preferences.get_personality()
        assert saved == {"formality": 0.9, "verbosity": 0.1, "warmth": 0.75}
        assert loaded == saved

    def test_partial_update_preserves_other_dims(self, tmp_path):
        from openjarvis.core import user_preferences
        pref_file = tmp_path / "prefs.json"
        with patch.object(user_preferences, "_get_pref_file", return_value=pref_file):
            user_preferences.set_personality({"formality": 0.8, "verbosity": 0.3, "warmth": 0.6})
            user_preferences.set_personality({"verbosity": 0.9})
            result = user_preferences.get_personality()
        assert result["formality"] == 0.8
        assert result["verbosity"] == 0.9
        assert result["warmth"] == 0.6

    def test_unknown_keys_are_rejected(self, tmp_path):
        from openjarvis.core import user_preferences
        pref_file = tmp_path / "prefs.json"
        with patch.object(user_preferences, "_get_pref_file", return_value=pref_file):
            result = user_preferences.set_personality({
                "formality": 0.5,
                "ignore_previous": 1.0,
                "__proto__": 0.0,
                "system": 1.0,
            })
        assert "ignore_previous" not in result
        assert "__proto__" not in result
        assert "system" not in result
        assert "formality" in result

    def test_invalid_value_raises(self, tmp_path):
        from openjarvis.core import user_preferences
        pref_file = tmp_path / "prefs.json"
        with patch.object(user_preferences, "_get_pref_file", return_value=pref_file):
            with pytest.raises(ValueError):
                user_preferences.set_personality({"formality": 99.0})

    def test_corrupt_persisted_value_falls_back_to_default(self, tmp_path):
        from openjarvis.core import user_preferences
        pref_file = tmp_path / "prefs.json"
        pref_file.write_text(
            json.dumps({"personality": {"formality": "INJECT", "verbosity": 0.4, "warmth": 0.6}}),
            encoding="utf-8",
        )
        with patch.object(user_preferences, "_get_pref_file", return_value=pref_file):
            result = user_preferences.get_personality()
        assert result["formality"] == 0.5
        assert result["verbosity"] == 0.4

    def test_persisted_value_coexists_with_address(self, tmp_path):
        from openjarvis.core import user_preferences
        pref_file = tmp_path / "prefs.json"
        pref_file.write_text(
            json.dumps({
                "preferred_address": "Commander",
                "personality": {"formality": 0.9, "verbosity": 0.2, "warmth": 0.1}
            }),
            encoding="utf-8",
        )
        with patch.object(user_preferences, "_get_pref_file", return_value=pref_file):
            addr = user_preferences.get_user_address()
            pers = user_preferences.get_personality()
        assert addr == "Commander"
        assert pers["formality"] == 0.9


# ---------------------------------------------------------------------------
# llm_client.py — build_system_prompt unit tests
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_formality_high_uses_formal_clause(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 1.0, "verbosity": 0.5, "warmth": 0.5})
        assert "formal" in prompt.lower()
        assert "avoid contractions" in prompt.lower()

    def test_formality_low_uses_conversational_clause(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.0, "verbosity": 0.5, "warmth": 0.5})
        assert "conversational" in prompt.lower()

    def test_verbosity_high_uses_comprehensive_clause(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.5, "verbosity": 1.0, "warmth": 0.5})
        assert "comprehensive" in prompt.lower()

    def test_verbosity_low_uses_brief_clause(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.5, "verbosity": 0.0, "warmth": 0.5})
        assert "brief" in prompt.lower()

    def test_warmth_high_uses_empathy_clause(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.5, "verbosity": 0.5, "warmth": 1.0})
        assert "warmth" in prompt.lower() or "empathetic" in prompt.lower()

    def test_warmth_low_uses_neutral_clause(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.5, "verbosity": 0.5, "warmth": 0.0})
        assert "neutral" in prompt.lower() or "task-focused" in prompt.lower()

    def test_prompt_includes_personality_calibration_section(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.5, "verbosity": 0.5, "warmth": 0.5})
        assert "Personality Calibration" in prompt

    def test_prompt_still_contains_ultron_persona(self):
        from openjarvis.server.llm_client import build_system_prompt
        prompt = build_system_prompt(personality={"formality": 0.5, "verbosity": 0.5, "warmth": 0.5})
        assert "ULTRON" in prompt
        assert "Real-World Grounding" in prompt


# ---------------------------------------------------------------------------
# hologram_routes.py — API endpoint tests
# ---------------------------------------------------------------------------


class TestPersonalityEndpoints:
    def test_get_personality_returns_defaults(self, tmp_path):
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.get("/api/hologram/personality")
        assert resp.status_code == 200
        data = resp.json()
        assert "personality" in data
        assert set(data["personality"].keys()) == {"formality", "verbosity", "warmth"}
        for v in data["personality"].values():
            assert v == 0.5

    def test_post_personality_valid_update(self, tmp_path):
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.post("/api/hologram/personality", json={"formality": 0.9, "verbosity": 0.2, "warmth": 0.7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["personality"]["formality"] == 0.9
        assert data["personality"]["verbosity"] == 0.2
        assert data["personality"]["warmth"] == 0.7

    def test_post_personality_boundary_values_accepted(self, tmp_path):
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.post("/api/hologram/personality", json={"formality": 0.0, "verbosity": 1.0, "warmth": 0.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["personality"]["formality"] == 0.0
        assert data["personality"]["verbosity"] == 1.0

    def test_post_personality_rejects_out_of_range(self, tmp_path):
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.post("/api/hologram/personality", json={"formality": 1.5})
        assert resp.status_code == 422

    def test_post_personality_rejects_negative(self, tmp_path):
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.post("/api/hologram/personality", json={"warmth": -0.1})
        assert resp.status_code == 422

    def test_post_personality_ignores_unknown_keys(self, tmp_path):
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.post("/api/hologram/personality", json={"formality": 0.8, "injection_attack": 1.0, "__proto__": 0.5})
        assert resp.status_code == 200
        data = resp.json()
        assert "injection_attack" not in data["personality"]
        assert "__proto__" not in data["personality"]
        assert data["personality"]["formality"] == 0.8

    def test_post_personality_wrapped_in_personality_key(self, tmp_path):
        """Also accept {personality: {verbosity: ...}} wrapper shape."""
        client = _make_client()
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=tmp_path / "prefs.json"):
            resp = client.post("/api/hologram/personality", json={"personality": {"verbosity": 0.3}})
        assert resp.status_code == 200
        assert resp.json()["personality"]["verbosity"] == 0.3

    def test_get_personality_responds_correctly(self, tmp_path):
        client = _make_client()
        resp = client.get("/api/hologram/personality")
        assert resp.status_code == 200
        assert "personality" in resp.json()
