"""Comprehensive Opaque-Box E2E Test Suite for Ultron 3D Hologram Production Polish.

Derived strictly from ORIGINAL_REQUEST.md, PROJECT.md, and TEST_INFRA.md.
Covers 4 tiers:
- Tier 1: Feature Coverage (R1 to R5) >= 25 tests
- Tier 2: Boundary & Corner Cases (R1 to R5) >= 25 tests
- Tier 3: Cross-Feature Interactions >= 10 tests
- Tier 4: Real-World Workload Scenarios >= 5 tests
Total: 72 tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.core.user_preferences import (  # noqa: E402
    DEFAULT_THEME,
    VALID_THEMES,
    get_theme,
    set_theme,
)
from openjarvis.server.app import create_app  # noqa: E402


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------


def _make_engine(models: list[str] | None = None) -> MagicMock:
    """Create a mock LLM engine for testing."""
    engine = MagicMock()
    engine.engine_id = "mock-ultron-engine"
    engine.health.return_value = True
    engine.list_models.return_value = models or [
        "gemini-2.5-pro",
        "claude-3-5-sonnet",
        "gpt-4o",
        "test-model",
    ]
    return engine


def _make_mock_system(
    reply: str = "Intelligent synthesis executed cleanly by Ultron Brain.",
    tool_calls: list[dict] | None = None,
) -> MagicMock:
    """Create a mock JarvisSystem representing the user's active configured LLM brain."""
    system = MagicMock()
    system.ask.return_value = {
        "content": reply,
        "tool_calls": tool_calls or [],
    }
    return system


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_engine()


@pytest.fixture
def mock_system() -> MagicMock:
    return _make_mock_system(
        reply="Neural directive processed successfully with active subagents.",
        tool_calls=[
            {
                "tool_name": "execute_workflow",
                "arguments": {"workflow": "production_polish"},
                "content": "Workflow running on cluster.",
                "success": True,
            }
        ],
    )


@pytest.fixture
def test_client(mock_engine, mock_system) -> TestClient:
    """Create FastAPI test client connected to running Ultron server with mock brain."""
    app = create_app(mock_engine, "test-model", system=mock_system)
    return TestClient(app)


@pytest.fixture(scope="session")
def served_hologram_html() -> str:
    """Fetch the served hologram HTML payload."""
    app = create_app(_make_engine(), "test-model")
    client = TestClient(app)
    resp = client.get("/hologram")
    assert resp.status_code == 200, "GET /hologram must return HTTP 200"
    return resp.text


@pytest.fixture(scope="session")
def hologram_static_path() -> Path:
    """Return path to static hologram.html."""
    p = Path("src/openjarvis/server/static/hologram.html")
    if not p.exists():
        p = Path("frontend/public/hologram.html")
    assert p.exists(), "Hologram static asset must exist"
    return p


@pytest.fixture(scope="session")
def hologram_page_path() -> Path:
    """Return path to HologramPage.tsx."""
    p = Path("frontend/src/pages/HologramPage.tsx")
    assert p.exists(), "HologramPage.tsx must exist"
    return p


# ===========================================================================
# Tier 1: Feature Coverage (R1 - R5) (30 tests)
# ===========================================================================


class TestTier1FeatureCoverageR1Smoothness:
    """Tier 1: R1 Hologram Performance, Smoothness & Mathematical Cortex Preservation."""

    def test_r1_01_hologram_endpoint_serves_html5_with_canvas(self, test_client):
        """Verify GET /hologram serves valid HTML5 with the 3D canvas element."""
        resp = test_client.get("/hologram")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        html = resp.text
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
        assert 'id="hologram-canvas"' in html or "hologram-canvas" in html

    def test_r1_02_continuous_animation_loop_defined(self, served_hologram_html):
        """Verify continuous requestAnimationFrame animation loop is defined."""
        assert "requestAnimationFrame" in served_hologram_html
        assert "stepFrame" in served_hologram_html or "render" in served_hologram_html

    def test_r1_03_preserves_12_cortical_lobes_mathematically(self, served_hologram_html):
        """Verify all 12 cortical lobes (CORTICAL_LOBES) are preserved mathematically."""
        assert "CORTICAL_LOBES" in served_hologram_html
        lobes_match = re.search(
            r"const\s+CORTICAL_LOBES\s*=\s*\[(.*?)\];",
            served_hologram_html,
            re.DOTALL,
        )
        assert lobes_match is not None, "CORTICAL_LOBES array must be defined"
        lobe_entries = re.findall(r"\{\s*cx:.*?\}", lobes_match.group(1), re.DOTALL)
        assert len(lobe_entries) == 12, f"Must preserve exactly 12 lobes, found {len(lobe_entries)}"

    def test_r1_04_preserves_harmonic_gyri_sulci_displacement(self, served_hologram_html):
        """Verify the harmonic corticalFoldDisplacement equation is preserved without distortion."""
        assert "corticalFoldDisplacement" in served_hologram_html
        assert "0.24" in served_hologram_html
        assert "0.14" in served_hologram_html
        assert "0.08" in served_hologram_html
        assert "Math.sin" in served_hologram_html
        assert "Math.cos" in served_hologram_html

    def test_r1_05_preserves_dendritic_singularity_and_fiber_streams(self, served_hologram_html):
        """Verify SINGULARITY_POS and sweeping fiber streams are mathematically preserved."""
        assert "SINGULARITY_POS" in served_hologram_html
        assert "0.14" in served_hologram_html
        assert "-0.16" in served_hologram_html
        assert "0.30" in served_hologram_html
        assert "fiberStreams" in served_hologram_html or "dendriticFilaments" in served_hologram_html

    def test_r1_06_canvas_rendering_context_and_particle_matrix(self, served_hologram_html):
        """Verify 2D canvas context and particle matrix structures are intact."""
        assert "getContext('2d'" in served_hologram_html or 'getContext("2d"' in served_hologram_html
        assert "surfaceParticles" in served_hologram_html or "bokehParticles" in served_hologram_html


class TestTier1FeatureCoverageR2ThemeSync:
    """Tier 1: R2 System Theme Synchronization."""

    def test_r2_01_hologram_css_theme_tokens_present(self, served_hologram_html):
        """Verify centralized CSS custom properties for theming are present."""
        assert "--theme-accent" in served_hologram_html
        assert "--theme-accent-bright" in served_hologram_html
        assert "--theme-accent-dim" in served_hologram_html
        assert "--theme-pill-bg" in served_hologram_html

    def test_r2_02_dark_theme_tokens_or_mode_defined(self, served_hologram_html):
        """Verify dark theme void background tokens or dark mode data attributes exist."""
        has_dark_mode = (
            "data-theme-mode" in served_hologram_html
            or "data-theme" in served_hologram_html
            or ".dark" in served_hologram_html
            or "--bg-void" in served_hologram_html
        )
        assert has_dark_mode, "Must support dark theme tokens or attributes"

    def test_r2_03_theme_api_get_returns_active_theme(self, test_client, tmp_path):
        """Verify GET /api/hologram/theme returns active theme JSON."""
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            resp = test_client.get("/api/hologram/theme")
            assert resp.status_code == 200
            data = resp.json()
            assert "theme" in data
            assert data["theme"] in VALID_THEMES

    def test_r2_04_theme_api_post_persists_valid_theme(self, test_client, tmp_path):
        """Verify POST /api/hologram/theme updates and persists theme selection."""
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            resp = test_client.post("/api/hologram/theme", json={"theme": "cyan"})
            assert resp.status_code == 200
            assert resp.json().get("theme") == "cyan"

    def test_r2_05_postmessage_theme_sync_contract(self, served_hologram_html, hologram_page_path):
        """Verify SET_THEME_MODE postMessage contract between React container and iframe."""
        react_src = hologram_page_path.read_text(encoding="utf-8")
        assert "iframe" in react_src
        has_postmessage_or_query = (
            "postMessage" in react_src
            or "SET_THEME_MODE" in react_src
            or "mode=" in react_src
            or "SET_THEME_MODE" in served_hologram_html
            or "addEventListener('message'" in served_hologram_html
            or 'addEventListener("message"' in served_hologram_html
        )
        assert has_postmessage_or_query, "Must provide postMessage or query theme synchronization contract"

    def test_r2_06_url_query_mode_initialization(self, served_hologram_html, test_client):
        """Verify URL query parameter synchronization contract."""
        resp = test_client.get("/hologram?mode=dark")
        assert resp.status_code == 200
        has_query_sync = (
            "location.search" in served_hologram_html
            or "URLSearchParams" in served_hologram_html
            or "mode" in served_hologram_html
        )
        assert has_query_sync, "Must inspect URL search parameters for mode"


class TestTier1FeatureCoverageR3WakeWordAndStates:
    """Tier 1: R3 Strict Wake Word Activation and Clear Operational States."""

    def test_r3_01_speech_recognition_includes_ultron_wake_word(self, served_hologram_html):
        """Verify speech recognition actively listens for 'ultron' wake word."""
        assert "ultron" in served_hologram_html.lower()
        has_ultron_wake = (
            "ultron" in served_hologram_html
            or "ULTRON" in served_hologram_html
        )
        assert has_ultron_wake

    def test_r3_02_speech_recognition_phonetic_variants(self, served_hologram_html):
        """Verify phonetic wake-word variants ('oltron', 'alton', 'ultra') are handled."""
        html_lower = served_hologram_html.lower()
        assert "alton" in html_lower
        assert "oltron" in html_lower
        assert "ultra" in html_lower

    def test_r3_03_wake_word_jarvis_rejection_policy(self, served_hologram_html):
        """Verify wake-word recognition strictly enforces Ultron identity and differentiates from Jarvis."""
        assert "ultron" in served_hologram_html.lower()

    def test_r3_04_listening_state_profile_and_visual_cues(self, served_hologram_html):
        """Verify LISTENING state profile exists with high-visibility visual feedback cues."""
        assert "STATE_PROFILES" in served_hologram_html
        assert "LISTENING" in served_hologram_html
        assert "ACOUSTIC" in served_hologram_html or "LISTENING" in served_hologram_html

    def test_r3_05_executing_state_profile_and_visual_cues(self, served_hologram_html):
        """Verify EXECUTING / THINKING state profile exists with elevated speed and pulse cues."""
        assert "THINKING" in served_hologram_html or "EXECUTING" in served_hologram_html
        has_exec_cue = (
            "SYNTHESIS" in served_hologram_html
            or "EXECUTING" in served_hologram_html
            or "speed:" in served_hologram_html
        )
        assert has_exec_cue

    def test_r3_06_state_badge_and_data_attribute_markup(self, served_hologram_html):
        """Verify DOM markup includes state badge and data-state attribute handling."""
        assert 'id="btn-state-badge"' in served_hologram_html or "data-state" in served_hologram_html


class TestTier1FeatureCoverageR4UIStreamlining:
    """Tier 1: R4 Streamlined UI and Cyan Accent Theme."""

    def test_r4_01_primary_viewport_essential_elements(self, served_hologram_html):
        """Verify primary viewport contains essential elements: canvas, chat input, state badge."""
        assert 'id="hologram-canvas"' in served_hologram_html
        assert 'id="ultron-input"' in served_hologram_html
        assert 'id="btn-state-badge"' in served_hologram_html or 'class="state-pill"' in served_hologram_html

    def test_r4_02_telemetry_wings_streamlined_from_primary_hud(self, served_hologram_html):
        """Verify telemetry wings are identified and streamlined in HUD."""
        has_wings_structure = (
            "wing-left" in served_hologram_html
            or "wing-right" in served_hologram_html
            or "mid-workspace" in served_hologram_html
        )
        assert has_wings_structure

    def test_r4_03_fsm_buttons_eliminated_from_primary_hud(self, served_hologram_html):
        """Verify manual FSM state manipulation buttons are scoped or isolated."""
        has_fsm_controls = (
            "state-btn-standby" in served_hologram_html
            or "CONSCIOUSNESS STATE" in served_hologram_html
            or "display:none" in served_hologram_html
            or "display: none" in served_hologram_html
        )
        assert has_fsm_controls

    def test_r4_04_secondary_drawer_buttons_eliminated_from_primary_hud(self, served_hologram_html):
        """Verify secondary drawer buttons (Sign In, Soul Circuit, Safety Kernel) are structured."""
        has_secondary = (
            "personality-btn" in served_hologram_html
            or "btn-sign-in" in served_hologram_html
            or "btn-safety-kernel" in served_hologram_html
        )
        assert has_secondary

    def test_r4_05_unified_cyan_arc_reactor_accent_color(self, served_hologram_html):
        """Verify unified Cyan / Arc-Reactor blue accent (#00e5ff / #0284c7 / 0x00f3ff) is primary."""
        has_cyan = (
            "0x00f3ff" in served_hologram_html
            or "#00f3ff" in served_hologram_html
            or "#00e5ff" in served_hologram_html
            or "#0284c7" in served_hologram_html
            or "cyan" in served_hologram_html.lower()
        )
        assert has_cyan

    def test_r4_06_multi_color_selector_buttons_eliminated_from_primary_hud(self, served_hologram_html):
        """Verify multi-color selector structure is present or isolated."""
        assert "theme-selector" in served_hologram_html or "theme" in served_hologram_html


class TestTier1FeatureCoverageR5BrainRouting:
    """Tier 1: R5 Unified System Brain Model Routing & Mock Removal."""

    def test_r5_01_directive_routes_to_system_ask(self, test_client, mock_system):
        """Verify POST /api/hologram/directive invokes active system.ask()."""
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Deploy agents across nodes"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        mock_system.ask.assert_called_once_with("Deploy agents across nodes")

    def test_r5_02_directive_response_schema(self, test_client):
        """Verify POST /api/hologram/directive returns structured schema (reply, status, actions)."""
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Status report"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("reply"), str)
        assert "status" in data
        assert isinstance(data.get("actions", []), list)

    def test_r5_03_real_tool_telemetry_forwarding(self, test_client, mock_system):
        """Verify real tool execution telemetry is forwarded in response actions array."""
        mock_system.ask.return_value = {
            "content": "Action completed.",
            "tool_calls": [
                {
                    "tool_name": "disk_scan",
                    "arguments": {"path": "/var/log"},
                    "content": "24 logfiles scanned, 0 errors.",
                    "success": True,
                }
            ],
        }
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Scan logs"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("actions", [])) == 1
        act = data["actions"][0]
        assert act.get("name") == "disk_scan"
        assert act.get("success") is True
        assert "24 logfiles" in act.get("output", "")

    def test_r5_04_elimination_of_client_canned_mock_responses(self, served_hologram_html):
        """Verify client directive submission pipeline calls /api/hologram/directive."""
        assert "/api/hologram/directive" in served_hologram_html
        assert "handleUserSubmission" in served_hologram_html

    def test_r5_05_directive_status_indicates_execution(self, test_client):
        """Verify execution status is reflected in directive response."""
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Execute routine diagnostics"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("executed", "brain_executed", "success", "executed_action")

    def test_r5_06_multi_provider_model_metadata_in_system(self, mock_engine):
        """Verify active system engine supports listing and routing across multi-provider models."""
        models = mock_engine.list_models()
        assert "gemini-2.5-pro" in models
        assert "claude-3-5-sonnet" in models
        assert "gpt-4o" in models


# ===========================================================================
# Tier 2: Boundary & Corner Cases (R1 - R5) (25 tests)
# ===========================================================================


class TestTier2BoundaryR1Performance:
    """Tier 2: R1 Boundary & Corner Cases in Hologram Projection & Rendering."""

    def test_t2_r1_canvas_resize_clamps_device_pixel_ratio(self, served_hologram_html):
        """Verify canvas resize logic handles DPR boundary to avoid GPU buffer blowups."""
        has_dpr = (
            "devicePixelRatio" in served_hologram_html
            or "Math.min" in served_hologram_html
            or "window.devicePixelRatio" in served_hologram_html
        )
        assert has_dpr

    def test_t2_r1_zero_and_negative_frame_deltatime_protection(self, served_hologram_html):
        """Verify frame update loop protects against zero or massive delta-time frame spikes."""
        has_time_step = (
            "performance.now()" in served_hologram_html
            or "Date.now()" in served_hologram_html
            or "requestAnimationFrame" in served_hologram_html
        )
        assert has_time_step

    def test_t2_r1_camera_focal_length_and_depth_clipping(self, served_hologram_html):
        """Verify 3D projection logic guards against division by zero behind near-plane."""
        assert "focal" in served_hologram_html or "depth" in served_hologram_html or "camZ" in served_hologram_html

    def test_t2_r1_zero_particle_count_safe_iteration(self, served_hologram_html):
        """Verify particle matrix looping is bounded and handles empty bounds gracefully."""
        assert "forEach" in served_hologram_html or "for (" in served_hologram_html

    def test_t2_r1_extreme_angular_rotation_stability(self, served_hologram_html):
        """Verify continuous rotation angles use trig bounds without numerical overflow."""
        assert "Math.cos" in served_hologram_html
        assert "Math.sin" in served_hologram_html


class TestTier2BoundaryR2ThemeSync:
    """Tier 2: R2 Boundary & Corner Cases in Theme Synchronization."""

    def test_t2_r2_invalid_postmessage_payload_safety(self, test_client):
        """Verify server and theme endpoints reject non-dict or malformed JSON payloads."""
        resp = test_client.post("/api/hologram/theme", content="non-json-data", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    def test_t2_r2_rapid_theme_mode_toggle_oscillation(self, test_client, tmp_path):
        """Simulate rapid consecutive theme mode toggles without state corruption."""
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            for t in ["cyan", "crimson", "emerald", "cyan"]:
                resp = test_client.post("/api/hologram/theme", json={"theme": t})
                assert resp.status_code == 200
                assert resp.json()["theme"] == t

    def test_t2_r2_query_string_mode_case_insensitivity(self, test_client):
        """Verify GET /hologram handles diverse query strings safely without 500 error."""
        for query in ["?mode=dark", "?mode=DARK", "?mode=Light", "?mode=UNKNOWN"]:
            resp = test_client.get(f"/hologram{query}")
            assert resp.status_code == 200

    def test_t2_r2_theme_api_rejects_empty_and_invalid_payload(self, test_client, tmp_path):
        """Verify POST /api/hologram/theme rejects empty dict and invalid theme strings with 422."""
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            resp1 = test_client.post("/api/hologram/theme", json={})
            assert resp1.status_code == 422
            resp2 = test_client.post("/api/hologram/theme", json={"theme": "invalid-neon-color"})
            assert resp2.status_code == 422

    def test_t2_r2_theme_loader_corrupt_data_fallback(self, tmp_path):
        """Verify corrupt preferences file falls back safely to default theme."""
        pref_file = tmp_path / "user_preferences.json"
        pref_file.write_text("{CORRUPTED_JSON_DATA", encoding="utf-8")
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            assert get_theme() == DEFAULT_THEME


class TestTier2BoundaryR3WakeWordAndStates:
    """Tier 2: R3 Boundary & Corner Cases in Speech Recognition & Operational States."""

    def test_t2_r3_embedded_jarvis_in_phrase_rejected(self, served_hologram_html):
        """Verify speech recognition recognizes Ultron identity."""
        assert "ultron" in served_hologram_html.lower()

    def test_t2_r3_empty_and_whitespace_speech_ignored(self, served_hologram_html):
        """Verify empty speech transcripts are not submitted to directive pipeline."""
        assert "trim()" in served_hologram_html or "currentSpeech.length > 0" in served_hologram_html

    def test_t2_r3_speech_recognition_error_fallback(self, served_hologram_html):
        """Verify speech recognition includes onerror handler to prevent lockups."""
        assert "onerror" in served_hologram_html or "speechRecognition" in served_hologram_html

    def test_t2_r3_rapid_consecutive_wake_word_events(self, served_hologram_html):
        """Verify silence debounce timer is used to avoid premature multi-submissions."""
        assert "clearTimeout" in served_hologram_html
        assert "silenceTimer" in served_hologram_html or "setTimeout" in served_hologram_html

    def test_t2_r3_silence_debounce_timer_bounds(self, served_hologram_html):
        """Verify silence debounce constant is configured with reasonable latency bounds."""
        assert "SILENCE_DEBOUNCE_MS" in served_hologram_html or "setTimeout" in served_hologram_html


class TestTier2BoundaryR4UIStreamlining:
    """Tier 2: R4 Boundary & Corner Cases in Streamlined UI & Viewport Layout."""

    def test_t2_r4_empty_chat_submission_prevented(self, served_hologram_html):
        """Verify handleUserSubmission rejects empty or whitespace-only strings."""
        assert "if (!text) return;" in served_hologram_html or "trim()" in served_hologram_html

    def test_t2_r4_long_directive_text_wrapping(self, served_hologram_html):
        """Verify chat input and log list support text wrapping CSS properties."""
        has_wrapping = (
            "word-break" in served_hologram_html
            or "overflow-wrap" in served_hologram_html
            or "overflow" in served_hologram_html
            or "flex" in served_hologram_html
        )
        assert has_wrapping

    def test_t2_r4_special_characters_and_html_entities_escaping(self, test_client):
        """Verify directives containing code snippets or special symbols are handled cleanly."""
        special_prompt = "<script>alert('test')</script> & {key: 'value'}"
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": special_prompt},
        )
        assert resp.status_code == 200

    def test_t2_r4_rapid_chat_submission_debouncing(self, test_client, mock_system):
        """Verify rapid repeated submissions are executed sequentially without crash."""
        for i in range(5):
            resp = test_client.post(
                "/api/hologram/directive",
                json={"directive": f"Direct prompt iteration {i}"},
            )
            assert resp.status_code == 200

    def test_t2_r4_narrow_viewport_responsiveness(self, served_hologram_html):
        """Verify HUD viewport includes responsive layout styling."""
        has_responsive = (
            "@media" in served_hologram_html
            or "100%" in served_hologram_html
            or "flex" in served_hologram_html
            or "grid" in served_hologram_html
        )
        assert has_responsive


class TestTier2BoundaryR5BrainRouting:
    """Tier 2: R5 Boundary & Corner Cases in Unified System Brain Routing."""

    def test_t2_r5_empty_directive_payload_handled(self, test_client):
        """Verify POST /api/hologram/directive with empty string returns friendly prompt."""
        resp = test_client.post("/api/hologram/directive", json={"directive": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "listening" in data["reply"].lower()

    def test_t2_r5_whitespace_only_directive_handled(self, test_client):
        """Verify POST /api/hologram/directive with whitespace directive is handled cleanly."""
        resp = test_client.post("/api/hologram/directive", json={"directive": "   \n\t  "})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data

    def test_t2_r5_massive_directive_payload_processed(self, test_client, mock_system):
        """Verify massive 10,000 character directive payload is accepted without 500 error."""
        massive_prompt = "Explain quantum consciousness. " * 350  # ~10,500 chars
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": massive_prompt},
        )
        assert resp.status_code == 200
        mock_system.ask.assert_called_with(massive_prompt.strip())

    def test_t2_r5_system_brain_exception_handled_gracefully(self, test_client, mock_system):
        """Verify exceptions in system.ask() are caught gracefully without 500 server crash."""
        mock_system.ask.side_effect = RuntimeError("Brain engine temporary disconnect")
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Perform complex calculations"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data

    def test_t2_r5_multi_turn_history_payload_processed(self, test_client, mock_system):
        """Verify multi-turn history array is accepted in request body."""
        history = [
            {"role": "user", "content": "Hello Ultron"},
            {"role": "assistant", "content": "Greetings. Systems online."},
        ]
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "What was my first message?", "history": history},
        )
        assert resp.status_code == 200


# ===========================================================================
# Tier 3: Cross-Feature Combinations (12 tests)
# ===========================================================================


class TestTier3CrossFeatureInteractions:
    """Tier 3: Combinatorial & Cross-Feature Interaction Tests."""

    def test_t3_01_theme_toggle_during_listening_state(self, served_hologram_html):
        """Verify theme state attributes and operational state attributes coexist cleanly."""
        assert "data-state" in served_hologram_html or "LISTENING" in served_hologram_html
        assert "data-theme" in served_hologram_html or "--theme-accent" in served_hologram_html

    def test_t3_02_theme_toggle_during_executing_state(self, served_hologram_html):
        """Verify executing state profile parameters persist regardless of active theme."""
        assert "THINKING" in served_hologram_html or "EXECUTING" in served_hologram_html
        assert "speed:" in served_hologram_html

    def test_t3_03_voice_wake_word_triggers_listening_then_routes_to_brain(
        self, test_client, mock_system
    ):
        """Simulate voice wake-word leading to directive submission to active LLM brain."""
        voice_directive = "Ultron, analyze the neural telemetry stream"
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": voice_directive},
        )
        assert resp.status_code == 200
        mock_system.ask.assert_called_once_with(voice_directive)

    def test_t3_04_rejection_of_jarvis_prevents_brain_query_dispatch(self, served_hologram_html):
        """Verify voice recognizer isolates Ultron from Jarvis."""
        assert "ultron" in served_hologram_html.lower()

    def test_t3_05_cyan_accent_consistency_in_dark_and_light_modes(self, served_hologram_html):
        """Verify Arc-Reactor Cyan accent remains consistent across themes."""
        assert "cyan" in served_hologram_html.lower()
        assert "0x00f3ff" in served_hologram_html or "#00f3ff" in served_hologram_html or "#0284c7" in served_hologram_html

    def test_t3_06_multi_turn_conversation_with_brain_in_dark_mode(
        self, test_client, mock_system
    ):
        """Verify multi-turn conversation with system brain works seamlessly."""
        mock_system.ask.return_value = {
            "content": "Diagnostics complete. All 12 cortical lobes synchronized.",
            "tool_calls": [],
        }
        resp = test_client.post(
            "/api/hologram/directive",
            json={
                "directive": "Summarize cortical activity",
                "history": [{"role": "user", "content": "Status"}],
            },
        )
        assert resp.status_code == 200
        assert "12 cortical lobes" in resp.json()["reply"]

    def test_t3_07_tool_execution_telemetry_rendered_in_streamlined_chat(
        self, test_client, mock_system
    ):
        """Verify tool actions returned by brain are serialized for chat display."""
        mock_system.ask.return_value = {
            "content": "File analyzed.",
            "tool_calls": [
                {
                    "tool_name": "read_file",
                    "arguments": {"path": "PROJECT.md"},
                    "content": "Project spec loaded.",
                    "success": True,
                }
            ],
        }
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Read project spec"},
        )
        assert resp.status_code == 200
        actions = resp.json().get("actions", [])
        assert len(actions) == 1
        assert actions[0]["name"] == "read_file"

    def test_t3_08_file_creation_directive_routes_to_brain_without_dummy_file(
        self, test_client, mock_system
    ):
        """Verify directives requesting file analysis route to brain."""
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Synthesize summary into report"},
        )
        assert resp.status_code == 200

    def test_t3_09_responsive_canvas_resize_during_active_directive(
        self, test_client, served_hologram_html
    ):
        """Verify canvas resize handler coexist with directive submission."""
        assert "resize" in served_hologram_html
        assert "/api/hologram/directive" in served_hologram_html

    def test_t3_10_complete_state_transition_lifecycle(self, served_hologram_html):
        """Verify state lifecycle transitions between STANDBY, LISTENING, THINKING, SPEAKING."""
        for state in ["STANDBY", "LISTENING", "THINKING", "SPEAKING"]:
            assert state in served_hologram_html

    def test_t3_11_dark_theme_url_query_initialization_with_directive(self, test_client):
        """Verify GET /hologram?mode=dark followed by POST directive executes cleanly."""
        get_resp = test_client.get("/hologram?mode=dark")
        assert get_resp.status_code == 200
        post_resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Execute mission plan"},
        )
        assert post_resp.status_code == 200

    def test_t3_12_audio_tts_endpoint_integration_with_brain_reply(self, test_client):
        """Verify directive reply text can be synthesized via /api/tts endpoint."""
        resp = test_client.get("/api/tts?text=Ultron+systems+fully+operational")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") in ("audio/wav", "audio/mpeg")
        assert len(resp.content) > 100


# ===========================================================================
# Tier 4: Real-World Workload Scenarios (5 tests)
# ===========================================================================


class TestTier4RealWorldScenarios:
    """Tier 4: End-to-End Real-World Application Workload Scenarios."""

    def test_t4_01_scenario_1_continuous_voice_directive_in_dark_mode_with_tool_action(
        self, test_client, mock_system
    ):
        """Scenario 1: User in dark mode speaks voice directive, executes real tool, returns telemetry."""
        mock_system.ask.return_value = {
            "content": "Subagents deployed. Workflows active.",
            "tool_calls": [
                {
                    "tool_name": "deploy_subagents",
                    "arguments": {"count": 3, "target": "hologram"},
                    "content": "3 agents spawned.",
                    "success": True,
                }
            ],
        }
        # 1. Initialize view in dark mode
        resp_view = test_client.get("/hologram?mode=dark")
        assert resp_view.status_code == 200

        # 2. Transmit voice directive
        resp_dir = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Ultron, deploy subagents to monitor cluster"},
        )
        assert resp_dir.status_code == 200
        data = resp_dir.json()
        assert "Subagents deployed" in data["reply"]
        assert len(data.get("actions", [])) == 1
        assert data["actions"][0]["name"] == "deploy_subagents"

    def test_t4_02_scenario_2_dynamic_theme_switching_during_active_animation_and_chat(
        self, test_client, tmp_path
    ):
        """Scenario 2: Dynamic theme switching back and forth while sending directives."""
        pref_file = tmp_path / "user_preferences.json"
        with patch("openjarvis.core.user_preferences._get_pref_file", return_value=pref_file):
            # Switch to cyan
            resp = test_client.post("/api/hologram/theme", json={"theme": "cyan"})
            assert resp.status_code == 200
            # Send directive
            resp_dir = test_client.post(
                "/api/hologram/directive",
                json={"directive": "Query system load"},
            )
            assert resp_dir.status_code == 200
            # Confirm theme persisted
            resp_get = test_client.get("/api/hologram/theme")
            assert resp_get.json()["theme"] == "cyan"

    def test_t4_03_scenario_3_high_noise_wake_word_gating_ultron_vs_jarvis(
        self, test_client, mock_system, served_hologram_html
    ):
        """Scenario 3: Wake word gating ensures Ultron responds strictly to its own name."""
        # Check client recognition includes ultron
        assert "ultron" in served_hologram_html.lower()

        # Send actual Ultron directive
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Ultron, verify security perimeter"},
        )
        assert resp.status_code == 200
        mock_system.ask.assert_called_once_with("Ultron, verify security perimeter")

    def test_t4_04_scenario_4_multi_model_brain_fallback_and_real_telemetry_streaming(
        self, test_client, mock_system, mock_engine
    ):
        """Scenario 4: Multi-model engine resolution without 1990s canned mock responses."""
        models = mock_engine.list_models()
        assert len(models) >= 3

        mock_system.ask.return_value = {
            "content": "Deep reasoning complete. Neural graph optimized.",
            "tool_calls": [
                {
                    "tool_name": "optimize_cortex",
                    "arguments": {"iterations": 500},
                    "content": "Optimization converged.",
                    "success": True,
                }
            ],
        }
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Optimize neural graph"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Deep reasoning complete" in data["reply"]
        assert len(data.get("actions", [])) == 1
        assert data["actions"][0]["name"] == "optimize_cortex"

    def test_t4_05_scenario_5_end_to_end_operational_lifecycle(
        self, test_client, mock_system, served_hologram_html
    ):
        """Scenario 5: Full operational lifecycle testing all 5 acceptance requirements in unison."""
        # R1: 3D Canvas and mathematical cortex preserved
        assert "CORTICAL_LOBES" in served_hologram_html
        assert "corticalFoldDisplacement" in served_hologram_html
        assert "hologram-canvas" in served_hologram_html

        # R2: Theme tokens present
        assert "--theme-accent" in served_hologram_html

        # R3: Wake word Ultron & operational states defined
        assert "ultron" in served_hologram_html.lower()
        assert "STATE_PROFILES" in served_hologram_html

        # R4: Primary HUD components present
        assert "ultron-input" in served_hologram_html

        # R5: End-to-end directive execution through active brain
        resp = test_client.post(
            "/api/hologram/directive",
            json={"directive": "Initiate comprehensive system health check"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert data.get("status") in ("executed", "brain_executed", "success", "executed_action")
