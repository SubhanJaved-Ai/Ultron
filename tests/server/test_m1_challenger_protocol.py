"""Empirical Challenger Test Suite: Theme Synchronization & postMessage Protocol Robustness.

Part of Milestone M1 Challenge (teamwork_challenger_m1_2).
Validates:
1. postMessage listener resilience under adversarial, malformed, and type-coercion payloads.
2. Rapid burst theme switching under high frequency (1,000+ events).
3. URL query parameter parsing under adversarial search strings (?mode=dark, ?mode=light, malformed, empty).
4. LocalStorage exception resilience (SecurityError, QuotaExceededError).
5. Echo loop prevention (emitBridge=false when called via UltronBridge).
6. React HologramPage.tsx contract conformance with PROJECT.md Contract 1.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Node.js Adversarial Test Harness Script
# ---------------------------------------------------------------------------

NODE_ADVERSARIAL_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('d:/Ultron/src/openjarvis/server/static/hologram.html', 'utf8');

// Minimal mock DOM & Browser environment
function createMockEnvironment(initialSearch = '', storageThrows = false) {
  const store = {};
  const listeners = {};
  const outboundMessages = [];

  const mockLocalStorage = {
    getItem: (key) => {
      if (storageThrows) throw new Error('SecurityError: Access Denied');
      return store[key] !== undefined ? store[key] : null;
    },
    setItem: (key, val) => {
      if (storageThrows) throw new Error('QuotaExceededError');
      store[key] = String(val);
    },
    removeItem: (key) => delete store[key],
    clear: () => { for (const k in store) delete store[k]; }
  };

  const documentElement = {
    classList: {
      classes: new Set(['dark']),
      toggle: function(cls, force) {
        if (force === undefined) {
          if (this.classes.has(cls)) this.classes.delete(cls);
          else this.classes.add(cls);
        } else if (force) {
          this.classes.add(cls);
        } else {
          this.classes.delete(cls);
        }
      },
      contains: function(cls) { return this.classes.has(cls); }
    },
    attributes: {},
    setAttribute: function(k, v) { this.attributes[k] = String(v); },
    getAttribute: function(k) { return this.attributes[k] || null; }
  };

  const body = {
    attributes: {},
    setAttribute: function(k, v) { this.attributes[k] = String(v); },
    getAttribute: function(k) { return this.attributes[k] || null; }
  };

  const document = {
    documentElement,
    body,
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: (id) => ({
      addEventListener: () => {},
      textContent: '',
      style: {},
      value: '',
      classList: { add: () => {}, remove: () => {} },
      getContext: () => ({
        clearRect: () => {},
        save: () => {},
        restore: () => {},
        beginPath: () => {},
        moveTo: () => {},
        lineTo: () => {},
        arc: () => {},
        stroke: () => {},
        fill: () => {},
        drawImage: () => {},
        createRadialGradient: () => ({ addColorStop: () => {} }),
        fillRect: () => {}
      }),
      width: 800,
      height: 600
    }),
    createElement: () => ({
      getContext: () => ({
        createRadialGradient: () => ({ addColorStop: () => {} }),
        fillRect: () => {}
      }),
      width: 64,
      height: 64
    })
  };

  const window = {
    location: { search: initialSearch },
    localStorage: mockLocalStorage,
    matchMedia: (query) => ({ matches: false }),
    addEventListener: (event, handler) => {
      listeners[event] = listeners[event] || [];
      listeners[event].push(handler);
    },
    removeEventListener: (event, handler) => {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter(h => h !== handler);
      }
    },
    dispatchEvent: (event) => {
      const type = event.type;
      if (listeners[type]) {
        for (const h of listeners[type]) h(event);
      }
    },
    parent: {
      postMessage: (msg, origin) => {
        outboundMessages.push({ msg, origin });
      }
    },
    devicePixelRatio: 1,
    innerWidth: 1024,
    innerHeight: 768
  };

  window.window = window;

  return { window, document, mockLocalStorage, store, listeners, outboundMessages, documentElement, body };
}

// Extract the script body from hologram.html
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/i);
if (!scriptMatch) {
  console.error(JSON.stringify({ error: "Could not find main script tag" }));
  process.exit(1);
}
const scriptContent = scriptMatch[1];

const results = {
  adversarialPayloads: [],
  rapidBurstPass: false,
  urlTests: [],
  storageResiliencePass: false,
  echoLoopPreventionPass: false
};

function createContextForEnv(env) {
  env.window.requestAnimationFrame = (cb) => 1;
  env.window.cancelAnimationFrame = () => {};
  env.window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });

  return vm.createContext({
    window: env.window,
    document: env.document,
    localStorage: env.mockLocalStorage,
    URLSearchParams: URLSearchParams,
    performance: { now: () => Date.now() },
    requestAnimationFrame: (cb) => 1,
    cancelAnimationFrame: () => {},
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    setTimeout: (fn) => setTimeout(fn, 0),
    clearTimeout: () => {},
    setInterval: () => {},
    clearInterval: () => {},
    console: console,
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    Float32Array: Float32Array,
    Math: Math
  });
}

// 1. Adversarial Payloads Test
{
  const env = createMockEnvironment('');
  const context = createContextForEnv(env);
  vm.runInContext(scriptContent, context);

  const testPayloads = [
    null,
    undefined,
    "",
    12345,
    true,
    false,
    [],
    {},
    { type: null },
    { type: 123 },
    { type: 'UNKNOWN_EVENT_TYPE' },
    { type: 'SET_THEME_MODE' }, // missing mode
    { type: 'SET_THEME_MODE', mode: null },
    { type: 'SET_THEME_MODE', mode: undefined },
    { type: 'SET_THEME_MODE', mode: 0 },
    { type: 'SET_THEME_MODE', mode: 1 },
    { type: 'SET_THEME_MODE', mode: true },
    { type: 'SET_THEME_MODE', mode: false },
    { type: 'SET_THEME_MODE', mode: {} },
    { type: 'SET_THEME_MODE', mode: [] },
    { type: 'SET_THEME_MODE', mode: 'light' },
    { type: 'SET_THEME_MODE', mode: 'dark' },
    { type: 'SET_THEME_MODE', mode: 'DARK' },
    { type: 'SET_THEME_MODE', mode: 'Light' },
    { type: 'SET_THEME_MODE', mode: 'cyan' },
    { type: 'SET_THEME_MODE', mode: 'invalid_mode' },
    { type: 'SET_THEME_MODE', mode: "<svg onload=alert(1)>" },
    { type: 'SET_THEME_MODE', mode: "'; DROP TABLE themes; --" },
    { type: 'SET_THEME_MODE', payload: 'light' },
    { type: 'SET_THEME_MODE', payload: 'dark' },
    { type: 'SET_THEME_MODE', payload: null },
    { type: 'SET_THEME_MODE', payload: { mode: 'light' } },
    { type: 'SET_THEME_MODE', __proto__: { evil: 'polluted' } }
  ];

  for (const payload of testPayloads) {
    try {
      env.window.dispatchEvent({ type: 'message', data: payload });
      const currentMode = env.documentElement.attributes['data-theme-mode'];
      results.adversarialPayloads.push({
        payload: typeof payload === 'object' ? JSON.stringify(payload) : String(payload),
        status: 'handled',
        modeResult: currentMode
      });
    } catch (err) {
      results.adversarialPayloads.push({
        payload: typeof payload === 'object' ? JSON.stringify(payload) : String(payload),
        status: 'crashed',
        error: err.message
      });
    }
  }
}

// 2. Rapid Burst Switching Test
{
  const env = createMockEnvironment('');
  const context = createContextForEnv(env);
  vm.runInContext(scriptContent, context);

  let success = true;
  for (let i = 0; i < 1000; i++) {
    const target = (i % 2 === 0) ? 'dark' : 'light';
    try {
      env.window.dispatchEvent({ type: 'message', data: { type: 'SET_THEME_MODE', mode: target } });
    } catch (err) {
      success = false;
      break;
    }
  }
  const finalMode = env.documentElement.attributes['data-theme-mode'];
  // After 1000 iterations (0 to 999), 999 % 2 is 1 -> 'light'
  results.rapidBurstPass = success && (finalMode === 'light');
}

// 3. URL Parameter Tests
{
  const urlCases = [
    { search: '?mode=dark', expected: 'dark' },
    { search: '?mode=light', expected: 'light' },
    { search: '?mode=invalid', expectedFallback: 'dark' },
    { search: '?mode=', expectedFallback: 'dark' },
    { search: '', expectedFallback: 'dark' }
  ];

  for (const c of urlCases) {
    const env = createMockEnvironment(c.search);
    const context = createContextForEnv(env);
    vm.runInContext(scriptContent, context);
    const mode = env.documentElement.attributes['data-theme-mode'];
    const expected = c.expected || c.expectedFallback;
    results.urlTests.push({ search: c.search, actual: mode, expected, pass: (mode === expected) });
  }
}

// 4. LocalStorage Exception Resilience
{
  const env = createMockEnvironment('', true); // storage throws
  const context = createContextForEnv(env);

  try {
    vm.runInContext(scriptContent, context);
    env.window.dispatchEvent({ type: 'message', data: { type: 'SET_THEME_MODE', mode: 'light' } });
    results.storageResiliencePass = (env.documentElement.attributes['data-theme-mode'] === 'light');
  } catch (e) {
    results.storageResiliencePass = false;
  }
}

// 5. Echo Loop Prevention
{
  const env = createMockEnvironment('');
  const context = createContextForEnv(env);
  vm.runInContext(scriptContent, context);

  // Clear initial messages
  env.outboundMessages.length = 0;

  // Receiving SET_THEME_MODE from parent
  env.window.dispatchEvent({ type: 'message', data: { type: 'SET_THEME_MODE', mode: 'light' } });

  // Outbound messages to parent must NOT contain THEME_MODE_CHANGED echo
  const echoMessages = env.outboundMessages.filter(m => m.msg && m.msg.type === 'THEME_MODE_CHANGED');
  results.echoLoopPreventionPass = (echoMessages.length === 0);
}

console.log(JSON.stringify(results));
"""


@pytest.fixture(scope="module")
def node_test_results() -> dict:
    """Runs the Node.js adversarial test harness and returns parsed JSON results."""
    proc = subprocess.run(
        ["node", "-e", NODE_ADVERSARIAL_HARNESS],
        capture_output=True,
        text=True,
        cwd="d:/Ultron",
        check=False,
    )
    assert proc.returncode == 0, f"Node script execution failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    data = json.loads(proc.stdout)
    return data


class TestAdversarialPostMessageProtocol:
    """Verifies that hologram.html safely handles all adversarial, malformed, and edge-case messages."""

    def test_zero_crashes_on_adversarial_payloads(self, node_test_results: dict):
        payloads = node_test_results.get("adversarialPayloads", [])
        assert len(payloads) > 25, "Expected at least 25 adversarial test cases"

        crashed = [p for p in payloads if p["status"] == "crashed"]
        assert len(crashed) == 0, f"Crashed on payloads: {crashed}"

    def test_valid_theme_mode_payloads_set_correct_mode(self, node_test_results: dict):
        payloads = node_test_results.get("adversarialPayloads", [])
        by_payload = {p["payload"]: p for p in payloads}

        # 'light' mode message sets light
        assert by_payload['{"type":"SET_THEME_MODE","mode":"light"}']["modeResult"] == "light"

        # 'dark' mode message sets dark
        assert by_payload['{"type":"SET_THEME_MODE","mode":"dark"}']["modeResult"] == "dark"

        # payload: 'light' sets light
        assert by_payload['{"type":"SET_THEME_MODE","payload":"light"}']["modeResult"] == "light"

    def test_malformed_and_unknown_modes_default_safely_to_dark(self, node_test_results: dict):
        payloads = node_test_results.get("adversarialPayloads", [])
        by_payload = {p["payload"]: p for p in payloads}

        # Null, numbers, injection attacks, and unknown strings default to dark (safe fallback)
        assert by_payload['{"type":"SET_THEME_MODE","mode":null}']["modeResult"] == "dark"
        assert by_payload['{"type":"SET_THEME_MODE","mode":12345}']["modeResult"] == "dark" or by_payload['{"type":"SET_THEME_MODE","mode":0}']["modeResult"] == "dark"
        assert by_payload['{"type":"SET_THEME_MODE","mode":"invalid_mode"}']["modeResult"] == "dark"
        assert by_payload['{"type":"SET_THEME_MODE","mode":"<svg onload=alert(1)>"}']["modeResult"] == "dark"

    def test_rapid_burst_theme_switching(self, node_test_results: dict):
        assert node_test_results.get("rapidBurstPass") is True, "Rapid 1,000-burst theme toggle failed"

    def test_url_parameter_initialization(self, node_test_results: dict):
        url_tests = node_test_results.get("urlTests", [])
        for t in url_tests:
            assert t["pass"] is True, f"URL test failed for {t['search']}: got {t['actual']}, expected {t['expected']}"

    def test_localstorage_failure_resilience(self, node_test_results: dict):
        assert node_test_results.get("storageResiliencePass") is True, "Storage failure crashed setThemeMode"

    def test_echo_loop_prevention(self, node_test_results: dict):
        assert node_test_results.get("echoLoopPreventionPass") is True, "Echo loop detected: iframe echoed parent theme event"


class TestReactParentContractConformance:
    """Verifies that HologramPage.tsx adheres strictly to PROJECT.md Contract 1."""

@pytest.fixture(scope="module")
def page_tsx_content() -> str:
    p = Path("d:/Ultron/frontend/src/pages/HologramPage.tsx")
    assert p.is_file(), f"HologramPage.tsx not found at {p}"
    return p.read_text(encoding="utf-8")

    def test_react_passes_theme_mode_query_param(self, page_tsx_content: str):
        assert "?mode=${currentMode}" in page_tsx_content or "?mode=" in page_tsx_content

    def test_react_posts_set_theme_mode_message(self, page_tsx_content: str):
        assert "postMessage({ type: 'SET_THEME_MODE', mode" in page_tsx_content or "postMessage({ type: 'SET_THEME_MODE'" in page_tsx_content

    def test_react_syncs_with_app_store(self, page_tsx_content: str):
        assert "useAppStore((s) => s.settings.theme)" in page_tsx_content
        assert "[themeSetting]" in page_tsx_content

    def test_react_has_dark_mode_tailwind_tokens(self, page_tsx_content: str):
        assert "dark:bg-slate-950" in page_tsx_content
        assert "dark:text-slate-100" in page_tsx_content
        assert "dark:bg-[#060b13]" in page_tsx_content
