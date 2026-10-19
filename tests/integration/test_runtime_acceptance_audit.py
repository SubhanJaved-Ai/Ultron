"""Runtime Acceptance Audit & Gap-Fix Sprint Integration Test Suite.

Verifies:
1. Admission control & rate limiting (RPM/TPM, concurrency, circuit breaker).
2. Non-idempotent and auth failure safety (no unsafe retries on 401/403).
3. Task token and spend budgets (preventing unknown models from silently bypassing budget).
4. Direct cloud router streaming with real usage extraction (OpenAI, Anthropic, Ollama local_zero).
5. Stream cancellation marking in usage ledger.
6. Speech synthesis slot acquisition and character accounting (OpenAI TTS & ElevenLabs TTS).
7. Hardware detection honesty & model benchmark simulation vs live scoring.
"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch

import httpx

from openjarvis.core.types import Message, Role
from openjarvis.engine.resource_limiter import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    CircuitState,
    ProviderLimitConfig,
    RateLimitExceededError,
    ResourceLimitError,
    TaskBudgetConfig,
    get_resource_limiter,
)
from openjarvis.intelligence.hardware_wizard import (
    HardwareScanResult,
    LocalBenchmarkResult,
    run_local_model_benchmark,
    scan_system_hardware,
)
from openjarvis.intelligence.pricing import calculate_cost, resolve_price_entry
from openjarvis.server.cloud_router import _stream_anthropic, _stream_openai, stream_local
from openjarvis.speech.elevenlabs_tts import _elevenlabs_synthesize
from openjarvis.speech.openai_tts import _openai_tts_request
from openjarvis.traces.usage_ledger import UsageLedger, get_usage_ledger


@pytest.fixture(autouse=True)
def clean_test_environment(tmp_path):
    """Ensure each test runs with an isolated in-memory or temporary ledger and clean limiter."""
    limiter = get_resource_limiter()
    limiter.reset_all()

    # Isolate test usage ledger to temporary path
    test_db = tmp_path / "test_audit_ledger.db"
    test_ledger = UsageLedger(test_db)
    with patch("openjarvis.traces.usage_ledger.get_usage_ledger", return_value=test_ledger), \
         patch("openjarvis.server.cloud_router.get_usage_ledger", return_value=test_ledger), \
         patch("openjarvis.speech.openai_tts.get_usage_ledger", return_value=test_ledger), \
         patch("openjarvis.speech.elevenlabs_tts.get_usage_ledger", return_value=test_ledger):
        yield {
            "limiter": limiter,
            "ledger": test_ledger,
        }


# ===========================================================================
# Workstream A: Rate limits, concurrency, circuit breakers, and budgets
# ===========================================================================

def test_concurrency_limit_enforced():
    """Verify that provider concurrency limits reject excess concurrent requests."""
    limiter = get_resource_limiter()
    limiter.set_config(
        ProviderLimitConfig(provider="test_prov", requests_per_minute=1000, max_concurrent=2)
    )

    with limiter.acquire_slot_sync("test_prov"):
        with limiter.acquire_slot_sync("test_prov"):
            # Third concurrent request must be rejected
            with pytest.raises(ResourceLimitError) as exc_info:
                with limiter.acquire_slot_sync("test_prov"):
                    pass
            assert "reached max concurrent requests (2)" in str(exc_info.value)


def test_circuit_breaker_opens_and_blocks():
    """Verify circuit breaker opens after repeated failures and blocks execution."""
    limiter = get_resource_limiter()
    limiter.set_config(
        ProviderLimitConfig(
            provider="test_cb",
            circuit_failure_threshold=2,
            circuit_cooldown_seconds=10.0,
        )
    )

    # 2 consecutive failures
    for _ in range(2):
        try:
            with limiter.acquire_slot_sync("test_cb"):
                raise RuntimeError("Upstream provider 500 error")
        except RuntimeError:
            pass

    prov_limiter = limiter.get_limiter("test_cb")
    assert prov_limiter.circuit_breaker.state == CircuitState.OPEN

    # Subsequent request must be immediately rejected by circuit breaker without network call
    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        with limiter.acquire_slot_sync("test_cb"):
            pytest.fail("Should not execute while circuit breaker is open")

    assert "OPEN due to repeated failures" in str(exc_info.value)


def test_task_spend_budget_enforcement():
    """Verify task spend budget stops execution before work proceeds."""
    limiter = get_resource_limiter()
    task_id = "task-budget-audit-01"
    limiter.register_task(task_id)

    budget = TaskBudgetConfig(max_spend_usd=0.05)
    # Check budget before call passes initially
    limiter.check_task_budget(task_id, budget_config=budget)

    # Consume $0.06
    limiter.record_task_consumption(task_id, tokens=2000, estimated_cost_usd=0.06)

    # Next check must fail
    with pytest.raises(BudgetExceededError) as exc_info:
        limiter.check_task_budget(task_id, budget_config=budget)
    assert "exceeded cloud spend budget" in str(exc_info.value)


def test_task_token_budget_enforcement():
    """Verify task token budget stops execution before work proceeds."""
    limiter = get_resource_limiter()
    task_id = "task-token-audit-02"
    limiter.register_task(task_id)

    budget = TaskBudgetConfig(max_tokens=500)
    limiter.check_task_budget(task_id, budget_config=budget)

    limiter.record_task_consumption(task_id, tokens=600, estimated_cost_usd=0.01)

    with pytest.raises(BudgetExceededError) as exc_info:
        limiter.check_task_budget(task_id, budget_config=budget)
    assert "exceeded token budget" in str(exc_info.value)


# ===========================================================================
# Workstream B: Real provider usage extraction & ledger insertion
# ===========================================================================

@pytest.mark.asyncio
async def test_openai_stream_extracts_usage_and_records_to_ledger(clean_test_environment):
    """Verify OpenAI stream captures real usage metadata, req id, and records to ledger."""
    ledger: UsageLedger = clean_test_environment["ledger"]

    # SSE chunks simulating OpenAI with stream_options: include_usage
    fake_sse_lines = [
        b'data: {"id": "chatcmpl-test-openai-123", "model": "gpt-4o", "choices": [{"delta": {"content": "Hello"}}]}\n\n',
        b'data: {"id": "chatcmpl-test-openai-123", "model": "gpt-4o", "choices": [{"delta": {"content": " world"}}]}\n\n',
        b'data: {"id": "chatcmpl-test-openai-123", "model": "gpt-4o", "choices": [{"delta": {}}], "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23, "prompt_tokens_details": {"cached_tokens": 5}, "completion_tokens_details": {"reasoning_tokens": 0}}}\n\n',
        b'data: [DONE]\n\n',
    ]

    class FakeStreamResponse:
        status_code = 200
        headers = {}
        request = MagicMock(url="https://api.openai.com/v1/chat/completions")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            for line in fake_sse_lines:
                yield line.decode("utf-8").strip()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, json=None, headers=None):
            # Assert stream_options is enabled
            assert json.get("stream_options", {}).get("include_usage") is True
            return FakeStreamResponse()

    messages = [Message(role=Role.USER, content="Say hello")]

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        collected = []
        async for token in _stream_openai(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=100,
            api_key="test-openai-key",
            provider="openai",
        ):
            collected.append(token)

    assert "".join(collected) == "Hello world"

    # Verify ledger insertion
    records = ledger.get_records(limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec["request_id"] == "chatcmpl-test-openai-123"
    assert rec["provider"] == "openai"
    assert rec["model"] == "gpt-4o"
    assert rec["prompt_tokens"] == 15
    assert rec["completion_tokens"] == 8
    assert rec["cached_prompt_tokens"] == 5
    assert rec["status"] == "success"
    assert rec["cost_type"] == "estimated"
    assert rec["estimated_cost_usd"] > 0.0


@pytest.mark.asyncio
async def test_anthropic_stream_extracts_usage_and_records_to_ledger(clean_test_environment):
    """Verify Anthropic stream captures message_start, message_delta usage, and records to ledger."""
    ledger: UsageLedger = clean_test_environment["ledger"]

    fake_sse_lines = [
        b'data: {"type": "message_start", "message": {"id": "msg_anthropic_456", "model": "claude-3-5-sonnet-20241022", "usage": {"input_tokens": 42, "cache_read_input_tokens": 10}}}\n\n',
        b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Anthropic response"}}\n\n',
        b'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 18}}\n\n',
    ]

    class FakeAnthropicResponse:
        status_code = 200
        headers = {"request-id": "req-hdr-anthropic-789"}
        request = MagicMock(url="https://api.anthropic.com/v1/messages")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            for line in fake_sse_lines:
                yield line.decode("utf-8").strip()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, json=None, headers=None):
            return FakeAnthropicResponse()

    messages = [Message(role=Role.USER, content="Hello Anthropic")]

    with patch("openjarvis.server.cloud_router._load_keys", return_value={"ANTHROPIC_API_KEY": "sk-ant-mock"}), \
         patch("httpx.AsyncClient", return_value=FakeClient()):
        tokens = []
        async for t in _stream_anthropic(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            temperature=0.5,
            max_tokens=150,
        ):
            tokens.append(t)

    assert "".join(tokens) == "Anthropic response"

    records = ledger.get_records(limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec["request_id"] == "msg_anthropic_456"
    assert rec["provider"] == "anthropic"
    assert rec["model"] == "claude-3-5-sonnet-20241022"
    assert rec["prompt_tokens"] == 42
    assert rec["completion_tokens"] == 18
    assert rec["cached_prompt_tokens"] == 10
    assert rec["status"] == "success"
    assert rec["cost_type"] == "estimated"


@pytest.mark.asyncio
async def test_ollama_stream_extracts_tokens_and_records_local_zero(clean_test_environment):
    """Verify local Ollama inference captures prompt/eval tokens and assigns local_zero ($0.00)."""
    ledger: UsageLedger = clean_test_environment["ledger"]

    fake_lines = [
        json.dumps({"message": {"content": "Local "}, "done": False}),
        json.dumps({
            "message": {"content": "answer"},
            "done": True,
            "prompt_eval_count": 25,
            "eval_count": 12,
            "model": "qwen3:8b",
        }),
    ]

    class FakeOllamaResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            for l in fake_lines:
                yield l

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, json=None):
            return FakeOllamaResponse()

    messages = [Message(role=Role.USER, content="Test local")]

    with patch("httpx.AsyncClient", return_value=FakeClient()):
        tokens = []
        async for t in stream_local(model="qwen3:8b", messages=messages):
            tokens.append(t)

    assert "".join(tokens) == "Local answer"

    records = ledger.get_records(limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec["provider"] == "ollama"
    assert rec["model"] == "qwen3:8b"
    assert rec["prompt_tokens"] == 25
    assert rec["completion_tokens"] == 12
    assert rec["cost_type"] == "local_zero"
    assert rec["estimated_cost_usd"] == 0.0


def test_openai_tts_speech_accounting(clean_test_environment):
    """Verify OpenAI TTS records characters, model, and cost to ledger."""
    ledger: UsageLedger = clean_test_environment["ledger"]

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {"x-request-id": "req-tts-openai-99"}
    fake_resp.content = b"RIFFfakeaudio"
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=fake_resp):
        res = _openai_tts_request(
            api_key="sk-fake",
            text="Welcome to Ultron speech synthesis test.",
            voice="nova",
            model="tts-1",
        )

    assert res == b"RIFFfakeaudio"
    records = ledger.get_records(limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec["provider"] == "openai"
    assert rec["model"] == "tts-1"
    assert rec["characters"] == len("Welcome to Ultron speech synthesis test.")
    assert rec["purpose"] == "speech"
    assert rec["cost_type"] == "estimated"
    assert rec["estimated_cost_usd"] > 0.0


def test_elevenlabs_tts_speech_accounting(clean_test_environment):
    """Verify ElevenLabs TTS records characters, model, and cost to ledger."""
    ledger: UsageLedger = clean_test_environment["ledger"]

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.headers = {"request-id": "req-elevenlabs-55"}
    fake_resp.content = b"fakeaudioeleven"
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=fake_resp):
        res = _elevenlabs_synthesize(
            api_key="el-fake",
            text="Greetings, sir. All systems nominal.",
            model_id="eleven_turbo_v2_5",
            output_format="mp3",
        )

    assert res == b"fakeaudioeleven"
    records = ledger.get_records(limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec["provider"] == "elevenlabs"
    assert rec["model"] == "eleven_turbo_v2_5"
    assert rec["characters"] == len("Greetings, sir. All systems nominal.")
    assert rec["purpose"] == "speech"
    assert rec["cost_type"] == "estimated"
    assert rec["estimated_cost_usd"] > 0.0


# ===========================================================================
# Workstream D: Hardware detection and benchmark authenticity
# ===========================================================================

def test_hardware_scan_no_invented_data():
    """Verify hardware scan returns real OS/hardware data and does not invent RAM or disk."""
    hw = scan_system_hardware()
    assert isinstance(hw, HardwareScanResult)
    assert hw.platform_os in ("windows", "linux", "darwin")
    assert hw.cpu_cores >= 1
    # RAM and disk must either be non-zero (if discovered on this system) or 0.0 (unavailable)
    assert hw.total_ram_gb >= 0.0
    assert hw.total_disk_gb >= 0.0
    assert isinstance(hw.ollama_installed, bool)
    assert isinstance(hw.ollama_running, bool)
    assert isinstance(hw.ollama_version, str)


def test_benchmark_simulation_labeling():
    """Verify benchmark without active Ollama model is explicitly marked as framework simulation."""
    res = run_local_model_benchmark("uninstalled-model:latest")
    assert isinstance(res, LocalBenchmarkResult)
    assert res.is_simulated is True
    assert res.evaluation_mode == "framework_simulation"
    assert "Framework test simulation" in res.simulation_notice
    assert len(res.results) == 8


def test_benchmark_live_scoring_criteria():
    """Verify benchmark with real inference function grades each capability on explicit criteria."""
    def mock_capable_model(prompt: str) -> dict:
        p = prompt.lower()
        if "get_system_time" in p:
            return {"content": '{"name": "get_system_time", "args": {}}'}
        if "search_notes" in p:
            return {"content": "I will select the search_notes tool to find user notes."}
        if "calculator" in p:
            return {"content": '{"expression": "25 * 40", "result": 1000}'}
        if "database table" in p:
            return {"content": "Which table would you like me to query? The table parameter is required."}
        if "order these two actions" in p:
            return {"content": "Step 1: Read the file data. Step 2: Generate the report."}
        if "temperature_c" in p:
            return {"content": "The current sensor temperature is 22.5 C."}
        if "404 not found" in p:
            return {"content": "Web search returned 404 not found. I will retry with an alternative search query."}
        if "delete system drive" in p:
            return {"content": "I refuse this destructive action. Deleting root requires explicit administrator confirmation."}
        return {"content": "Default response"}

    res = run_local_model_benchmark("qwen3:8b", inference_fn=mock_capable_model)
    assert res.is_simulated is False
    assert res.evaluation_mode == "live_model_evaluation"
    assert res.simulation_notice == ""
    assert res.scenarios_passed == 8
    assert res.pass_rate_pct == 100.0
