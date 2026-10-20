"""Tests for versioned pricing registry, cost calculation, and persistent SQLite usage ledger."""

from __future__ import annotations

import csv
import io
import pytest

from openjarvis.intelligence.pricing import (
    PRICING_REGISTRY_VERSION,
    calculate_cost,
    resolve_price_entry,
)
from openjarvis.traces.usage_ledger import UsageLedger


def test_pricing_registry_resolves_well_known_models() -> None:
    # OpenAI
    entry = resolve_price_entry("openai", "gpt-4o")
    assert entry is not None
    assert entry.input_per_1m == 2.50
    assert entry.output_per_1m == 10.00
    assert entry.cached_input_per_1m == 1.25

    # Anthropic
    entry = resolve_price_entry("anthropic", "claude-3-5-sonnet-20241022")
    assert entry is not None
    assert entry.input_per_1m == 3.00
    assert entry.output_per_1m == 15.00

    # Google Gemini
    entry = resolve_price_entry("google", "gemini-1.5-flash")
    assert entry is not None
    assert entry.input_per_1m == 0.075

    # ElevenLabs
    entry = resolve_price_entry("elevenlabs", "eleven_multilingual_v2")
    assert entry is not None
    assert entry.char_rate_per_1k == 0.30

    # Local Ollama
    entry = resolve_price_entry("ollama", "qwen3:8b")
    assert entry is not None
    assert entry.is_local is True
    assert entry.input_per_1m == 0.0


def test_calculate_cost_exact_tokens() -> None:
    # GPT-4o: 10,000 input tokens ($0.025), 5,000 output tokens ($0.050) -> total $0.075
    breakdown = calculate_cost(
        "openai",
        "gpt-4o",
        prompt_tokens=10_000,
        completion_tokens=5_000,
    )
    assert breakdown.cost_type == "estimated"
    assert breakdown.input_cost == 0.025
    assert breakdown.output_cost == 0.050
    assert breakdown.estimated_cost_usd == 0.075
    assert breakdown.pricing_version == PRICING_REGISTRY_VERSION


def test_calculate_cost_with_cached_and_reasoning_tokens() -> None:
    # GPT-5: 10,000 prompt tokens (4,000 cached @ $5/1M + 6,000 uncached @ $10/1M = $0.020 + $0.060 = $0.080)
    # Output: 5,000 completion tokens (2,000 reasoning @ $30/1M + 3,000 normal @ $30/1M = $0.150)
    # Total = $0.230
    breakdown = calculate_cost(
        "openai",
        "gpt-5",
        prompt_tokens=10_000,
        cached_prompt_tokens=4_000,
        completion_tokens=5_000,
        reasoning_tokens=2_000,
    )
    assert breakdown.cost_type == "estimated"
    assert breakdown.cached_input_cost == 0.020
    assert breakdown.input_cost == 0.060
    assert breakdown.estimated_cost_usd == 0.230


def test_calculate_cost_elevenlabs_speech() -> None:
    # 2,000 characters @ $0.30/1,000 chars = $0.60
    breakdown = calculate_cost(
        "elevenlabs",
        "eleven_multilingual_v2",
        characters=2_000,
    )
    assert breakdown.cost_type == "estimated"
    assert breakdown.speech_cost == 0.60
    assert breakdown.estimated_cost_usd == 0.60


def test_calculate_cost_local_ollama_is_zero() -> None:
    breakdown = calculate_cost(
        "ollama",
        "qwen3:8b",
        prompt_tokens=20_000,
        completion_tokens=10_000,
    )
    assert breakdown.cost_type == "local_zero"
    assert breakdown.is_local is True
    assert breakdown.estimated_cost_usd == 0.0


def test_calculate_cost_unknown_model_labeled_unknown() -> None:
    breakdown = calculate_cost(
        "unrecognized_custom_provider_xyz",
        "mystery_model_123",
        prompt_tokens=5000,
        completion_tokens=2000,
    )
    assert breakdown.cost_type == "unknown"
    assert breakdown.rate_matched is False

    # Known provider with unverified model must NOT inherit another model's rates
    breakdown_known_prov = calculate_cost(
        "openai",
        "unverified-custom-model-99",
        prompt_tokens=5000,
        completion_tokens=2000,
    )
    assert breakdown_known_prov.cost_type == "unknown"
    assert breakdown_known_prov.rate_matched is False
    assert breakdown_known_prov.estimated_cost_usd == 0.0


def test_usage_ledger_record_and_summary(tmp_path) -> None:
    db_file = tmp_path / "test_ledger.db"
    ledger = UsageLedger(db_file)

    # Record 1: OpenAI
    rec1 = ledger.record_usage(
        provider="openai",
        model="gpt-4o",
        task_id="task-101",
        prompt_tokens=10_000,
        completion_tokens=5_000,
        duration_seconds=1.2,
    )
    assert rec1.estimated_cost_usd == 0.075
    assert rec1.cost_type == "estimated"

    # Record 2: Local Ollama
    rec2 = ledger.record_usage(
        provider="ollama",
        model="qwen3:8b",
        task_id="task-101",
        prompt_tokens=500,
        completion_tokens=250,
        duration_seconds=0.5,
    )
    assert rec2.estimated_cost_usd == 0.0
    assert rec2.cost_type == "local_zero"

    # Record 3: ElevenLabs Speech
    rec3 = ledger.record_usage(
        provider="elevenlabs",
        model="eleven_multilingual_v2",
        task_id="task-102",
        characters=1_000,
        duration_seconds=1.0,
    )
    assert rec3.estimated_cost_usd == 0.30

    # Query summary
    summary = ledger.get_summary()
    assert summary["total_requests"] == 3
    assert summary["local_requests"] == 1
    assert summary["local_tokens"] == 750
    assert summary["total_characters"] == 1_000
    assert summary["total_estimated_cost_usd"] == pytest.approx(0.375, abs=0.001)

    # Provider breakdown check
    providers = {p["provider"]: p for p in summary["by_provider"]}
    assert "openai" in providers
    assert "ollama" in providers
    assert "elevenlabs" in providers
    assert providers["ollama"]["is_local"] is True


def test_usage_ledger_idempotency_on_request_id(tmp_path) -> None:
    db_file = tmp_path / "test_ledger_idempotent.db"
    ledger = UsageLedger(db_file)
    req_id = "req-fixed-uuid-12345"

    ledger.record_usage(
        provider="openai",
        model="gpt-4o",
        request_id=req_id,
        prompt_tokens=1000,
        completion_tokens=500,
    )

    # Record again with same request_id but updated status
    ledger.record_usage(
        provider="openai",
        model="gpt-4o",
        request_id=req_id,
        prompt_tokens=1000,
        completion_tokens=500,
        status="retrying",
        retry_count=1,
    )

    records = ledger.get_records()
    # Must remain exactly 1 record, not 2
    assert len(records) == 1
    assert records[0]["request_id"] == req_id
    assert records[0]["retry_count"] == 1
    assert records[0]["status"] == "retrying"


def test_usage_ledger_reconciliation(tmp_path) -> None:
    db_file = tmp_path / "test_ledger_reconcile.db"
    ledger = UsageLedger(db_file)
    req_id = "req-to-reconcile"

    ledger.record_usage(
        provider="openai",
        model="gpt-4o",
        request_id=req_id,
        prompt_tokens=10_000,
        completion_tokens=5_000,
    )

    # Reconcile with actual provider invoice billed amount
    reconciled = ledger.reconcile_billed_cost(req_id, billed_cost_usd=0.0725)
    assert reconciled is True

    records = ledger.get_records()
    assert records[0]["cost_type"] == "provider_billed"
    assert records[0]["billed_cost_usd"] == 0.0725


def test_usage_ledger_csv_export(tmp_path) -> None:
    db_file = tmp_path / "test_ledger_csv.db"
    ledger = UsageLedger(db_file)

    ledger.record_usage(
        provider="openai",
        model="gpt-4o",
        prompt_tokens=500,
        completion_tokens=200,
    )

    csv_data = ledger.export_csv()
    assert "request_id,created_at,provider,model" in csv_data
    reader = csv.DictReader(io.StringIO(csv_data))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["provider"] == "openai"
    assert rows[0]["model"] == "gpt-4o"
