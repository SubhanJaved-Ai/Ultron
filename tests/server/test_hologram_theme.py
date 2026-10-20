"""Unit tests for TSK-P5-03 — Tri-Theme Hologram HUD.

Covers:
- Theme validation (_validate_theme: cyan, crimson, emerald, case-insensitive, rejection of invalid/non-string).
- Persistence round-trip via get_theme / set_theme (defaults, updates, preservation of other keys, corrupt file fallback).
- GET  /api/hologram/theme endpoint (default, after update).
- POST /api/hologram/theme endpoint (valid themes, rejection of invalid values with HTTP 422).
- Hologram HUD HTML structure: presence of theme selector, buttons, CSS tokens, and WebGL palette mappings.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.core.user_preferences import (  # noqa: E402
    DEFAULT_THEME,
    VALID_THEMES,
    _validate_theme,
    get_theme,
    set_theme,
)
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
# Theme Validation Tests
# ---------------------------------------------------------------------------


class TestValidateTheme:
    def test_valid_cyan(self):
        assert _validate_theme("cyan") == "cyan"

    def test_valid_crimson(self):
        assert _validate_theme("crimson") == "crimson"

    def test_valid_emerald(self):
        assert _validate_theme("emerald") == "emerald"

    def test_case_insensitivity(self):
        assert _validate_theme("CYAN") == "cyan"
        assert _validate_theme("Crimson") == "crimson"
        assert _validate_theme("EMERALD") == "emerald"

    def test_whitespace_stripping(self):
        assert _validate_theme("  cyan  ") == "cyan"
        assert _validate_theme("\tcrimson\n") == "crimson"

    def test_constants_structure(self):
        assert DEFAULT_THEME == "cyan"
        assert set(VALID_THEMES) == {"cyan", "crimson", "emerald"}

    @pytest.mark.parametrize("invalid", [
        "purple",
        "blue",
        "magenta",
        "gold",
        "",
        "   ",
        "../cyan",
        "<script>alert(1)</script>",
    ])
    def test_invalid_theme_strings_raise(self, invalid):
        with pytest.raises(ValueError, match="Invalid theme"):
            _validate_theme(invalid)

    @pytest.mark.parametrize("non_string", [
        None,
        123,
        1.0,
        [],
        {},
        True,
        False,
    ])
    def test_non_string_types_raise(self, non_string):
        with pytest.raises(ValueError, match="must be a string"):
            _validate_theme(non_string)


# ---------------------------------------------------------------------------
# Theme Persistence Tests (Isolated with tmp_path)
# ---------------------------------------------------------------------------


class TestThemePersistence:
    def test_default_theme_when_no_file(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            assert get_theme() == "cyan"

    def test_set_and_get_roundtrip_all_themes(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            for theme in ("cyan", "crimson", "emerald"):
                saved = set_theme(theme)
                assert saved == theme
                assert get_theme() == theme

    def test_set_theme_preserves_other_preference_keys(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        pref_file.write_text(
            json.dumps({
                "preferred_address": "Commander",
                "personality": {"formality": 0.8, "verbosity": 0.2, "warmth": 0.5},
            }),
            encoding="utf-8",
        )
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            set_theme("emerald")
            assert get_theme() == "emerald"

            # Verify other keys are preserved in file
            data = json.loads(pref_file.read_text(encoding="utf-8"))
            assert data["preferred_address"] == "Commander"
            assert data["personality"]["formality"] == 0.8
            assert data["theme"] == "emerald"

    def test_corrupt_file_falls_back_to_default(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        pref_file.write_text("{CORRUPT JSON", encoding="utf-8")
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            assert get_theme() == "cyan"

    def test_corrupt_theme_value_in_file_falls_back_to_default(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        pref_file.write_text(json.dumps({"theme": "neon-purple"}), encoding="utf-8")
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            assert get_theme() == "cyan"

    def test_set_theme_rejects_invalid_value(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            with pytest.raises(ValueError):
                set_theme("invalid_theme")


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------


class TestThemeEndpoints:
    def test_get_theme_returns_default(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            client = _make_client()
            resp = client.get("/api/hologram/theme")
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("theme") == "cyan"

    def test_post_theme_updates_and_persists(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            client = _make_client()

            # Set to crimson
            resp = client.post("/api/hologram/theme", json={"theme": "crimson"})
            assert resp.status_code == 200
            assert resp.json().get("theme") == "crimson"

            # Verify GET reflects crimson
            get_resp = client.get("/api/hologram/theme")
            assert get_resp.status_code == 200
            assert get_resp.json().get("theme") == "crimson"

            # Set to emerald
            resp2 = client.post("/api/hologram/theme", json={"theme": "emerald"})
            assert resp2.status_code == 200
            assert resp2.json().get("theme") == "emerald"

            # Verify GET reflects emerald
            get_resp2 = client.get("/api/hologram/theme")
            assert get_resp2.status_code == 200
            assert get_resp2.json().get("theme") == "emerald"

    def test_post_theme_rejects_invalid_theme_with_422(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            client = _make_client()
            resp = client.post("/api/hologram/theme", json={"theme": "neon-violet"})
            assert resp.status_code == 422
            detail = resp.json().get("detail", "")
            assert "Invalid theme" in detail

    def test_post_theme_rejects_non_string_with_422(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            client = _make_client()
            resp = client.post("/api/hologram/theme", json={"theme": 999})
            assert resp.status_code == 422

    def test_post_theme_rejects_missing_payload(self, tmp_path):
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            client = _make_client()
            resp = client.post("/api/hologram/theme", json={})
            assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Hologram HUD HTML & Token Tests
# ---------------------------------------------------------------------------


class TestThemeHtmlAndTokens:
    def test_hud_html_contains_theme_selector_controls(self):
        client = _make_client()
        resp = client.get("/hologram")
        assert resp.status_code == 200
        html = resp.text

        # Container
        assert 'id="theme-selector"' in html
        assert 'class="theme-selector-pill"' in html

        # Individual theme buttons
        assert 'id="theme-btn-cyan"' in html
        assert 'id="theme-btn-crimson"' in html
        assert 'id="theme-btn-emerald"' in html
        assert "CYAN" in html
        assert "CRIMSON" in html
        assert "EMERALD" in html

    def test_hud_html_contains_centralized_css_tokens(self):
        client = _make_client()
        resp = client.get("/hologram")
        assert resp.status_code == 200
        html = resp.text

        # CSS theme tokens defined for root and theme scopes
        assert "--theme-accent" in html
        assert "--theme-accent-bright" in html
        assert "--theme-accent-dim" in html
        assert "--theme-accent-border" in html
        assert "--theme-accent-glow" in html
        assert "--theme-pill-bg" in html
        assert "--theme-pill-text" in html

        # Theme selectors
        assert '[data-theme="cyan"]' in html
        assert '[data-theme="crimson"]' in html
        assert '[data-theme="emerald"]' in html

    def test_hud_html_contains_threejs_palettes_and_controller(self):
        client = _make_client()
        resp = client.get("/hologram")
        assert resp.status_code == 200
        html = resp.text

        # WebGL theme palettes
        assert "THEME_PALETTES" in html
        assert "0x00f3ff" in html  # Cyan primary
        assert "0xff2a4b" in html  # Crimson primary
        assert "0x00ff88" in html  # Emerald primary

        # Controller functions
        assert "setHologramTheme" in html
        assert "_loadHologramTheme" in html
        assert "ultron_hologram_theme" in html
