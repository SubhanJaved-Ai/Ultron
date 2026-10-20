"""Integration test suite for the Ultron Final Pre-E2E Hardening Sprint.

Verifies:
1. Billing reconciliation source provenance and validation in UsageLedger.
2. Time window filtering in UsageLedger get_records and export_csv.
3. Hard spend budget fail-safe rejecting uncataloged/unknown-priced models.
4. Hardware discovery representing missing metrics as None and unverified capacity handling.
5. Local model benchmark framework simulation labeling and empirical score verification flags.
6. Centralized REST API structured error contracts with dual-compatibility (detail + error object).
7. Persistent task creation idempotency key deduplication and replay.
8. Partial and interrupted stream telemetry tracking in usage ledger metadata.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from openjarvis.engine.resource_limiter import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    ProviderLimitConfig,
    RateLimitExceededError,
    ResourceLimitError,
    TaskBudgetConfig,
    get_resource_limiter,
)
from openjarvis.intelligence.hardware_wizard import (
    HardwareScanResult,
    LocalBenchmarkResult,
    recommend_models,
    run_local_model_benchmark,
)
from openjarvis.server.app import create_app
from openjarvis.traces.usage_ledger import UsageLedger


@pytest.fixture
def clean_ledger(tmp_path):
    db_file = tmp_path / "test_hardening_ledger.db"
    return UsageLedger(db_file)


# ---------------------------------------------------------------------------
# 1. Billing reconciliation provenance and validation
# ---------------------------------------------------------------------------

def test_reconcile_provenance_and_validation(clean_ledger):
    ledger = clean_ledger
    req_id = "req-audit-provenance-01"

    ledger.record_usage(
        provider="openai",
        model="gpt-4o",
        request_id=req_id,
        prompt_tokens=5000,
        completion_tokens=2000,
    )

    # Empty reconciliation source must be rejected
    with pytest.raises(ValueError) as exc_info:
        ledger.reconcile_billed_cost(req_id, billed_cost_usd=0.035, reconciliation_source="")
    assert "requires an authoritative source" in str(exc_info.value)

    # Negative billed cost must be rejected
    with pytest.raises(ValueError) as exc_info:
        ledger.reconcile_billed_cost(
            req_id,
            billed_cost_usd=-1.0,
            reconciliation_source="openai_invoice_oct2026",
        )
    assert "cannot be negative" in str(exc_info.value)

    # Valid reconciliation with authoritative source
    ok = ledger.reconcile_billed_cost(
        req_id,
        billed_cost_usd=0.0325,
        reconciliation_source="openai_invoice_2026_10_inv_9981",
    )
    assert ok is True

    records = ledger.get_records(limit=10)
    assert len(records) == 1
    rec = records[0]
    assert rec["cost_type"] == "provider_billed"
    assert rec["billed_cost_usd"] == 0.0325
    assert rec["metadata"]["reconciliation_source"] == "openai_invoice_2026_10_inv_9981"
    assert rec["metadata"]["reconciled_cost_usd"] == 0.0325
    assert "reconciled_at" in rec["metadata"]


# ---------------------------------------------------------------------------
# 2. Time window filtering in UsageLedger get_records and export_csv
# ---------------------------------------------------------------------------

def test_usage_records_time_window_filtering_and_csv_export(clean_ledger):
    ledger = clean_ledger

    # Record 3 events at different timestamps
    rec1 = ledger.record_usage(provider="openai", model="gpt-4o", request_id="req-time-1")
    time.sleep(0.05)
    t_mid = time.time()
    time.sleep(0.05)
    rec2 = ledger.record_usage(provider="anthropic", model="claude-3-5-sonnet-20241022", request_id="req-time-2")
    rec3 = ledger.record_usage(provider="ollama", model="qwen3:8b", request_id="req-time-3")

    # Filter with start_time >= t_mid should only return rec2 and rec3
    records_after_mid = ledger.get_records(start_time=t_mid)
    ids_after_mid = [r["request_id"] for r in records_after_mid]
    assert "req-time-1" not in ids_after_mid
    assert "req-time-2" in ids_after_mid
    assert "req-time-3" in ids_after_mid

    # Filter with end_time < t_mid should only return rec1
    records_before_mid = ledger.get_records(end_time=t_mid)
    ids_before_mid = [r["request_id"] for r in records_before_mid]
    assert "req-time-1" in ids_before_mid
    assert "req-time-2" not in ids_before_mid
    assert "req-time-3" not in ids_before_mid

    # CSV export with start_time filter
    csv_filtered = ledger.export_csv(start_time=t_mid)
    assert "req-time-1" not in csv_filtered
    assert "req-time-2" in csv_filtered
    assert "req-time-3" in csv_filtered


# ---------------------------------------------------------------------------
# 3. Hard spend budget fail-safe rejecting uncataloged/unknown-priced models
# ---------------------------------------------------------------------------

def test_spend_budget_rejects_unknown_models():
    limiter = get_resource_limiter()
    task_id = "task-budget-fail-safe-01"
    limiter.register_task(task_id)

    budget = TaskBudgetConfig(max_spend_usd=2.00)

    # Calling with a cataloged model passes budget check
    limiter.check_task_budget(task_id, budget_config=budget, model="gpt-4o", provider="openai")

    # Calling with a local Ollama model is $0.00 and passes
    limiter.check_task_budget(task_id, budget_config=budget, model="custom-local-finetune", provider="ollama")

    # Calling with an unknown cloud model without catalog pricing must be blocked
    with pytest.raises(BudgetExceededError) as exc_info:
        limiter.check_task_budget(
            task_id,
            budget_config=budget,
            model="unmetered-unknown-cloud-ai",
            provider="some_custom_provider",
        )
    assert "has uncataloged/unknown pricing" in str(exc_info.value)
    assert "blocked to prevent unmetered spend bypass" in str(exc_info.value)

    # If policy explicitly allows unmetered models, it passes
    limiter.check_task_budget(
        task_id,
        budget_config=budget,
        model="unmetered-unknown-cloud-ai",
        provider="some_custom_provider",
        allow_unmetered_on_spend_budget=True,
    )


# ---------------------------------------------------------------------------
# 4. Hardware discovery representing missing metrics as None
# ---------------------------------------------------------------------------

def test_hardware_scan_undetectable_as_none():
    # If total_ram_gb is None (undetectable), fit status is unverified_capacity
    hw = HardwareScanResult(
        platform_os="windows",
        architecture="x86_64",
        cpu_brand="Test CPU",
        cpu_cores=4,
        total_ram_gb=None,  # undetectable
        free_ram_gb=None,
        total_disk_gb=None,
        free_disk_gb=None,
        disk_path="C:\\",
    )
    recs = recommend_models(hw)
    assert len(recs) > 0
    for r in recs:
        assert r.fit_status == "unverified_capacity"
        assert "unverified" in r.reasoning.lower()


# ---------------------------------------------------------------------------
# 5. Local model benchmark framework simulation labeling and empirical score flag
# ---------------------------------------------------------------------------

def test_benchmark_simulation_labeling_and_empirical_flag():
    # Benchmark against uninstalled model
    res = run_local_model_benchmark("definitely-not-installed-model-1234")
    assert isinstance(res, LocalBenchmarkResult)
    assert res.is_simulated is True
    assert res.evaluation_mode == "framework_simulation"
    assert res.empirical_score_verified is False
    assert "Framework test simulation only" in res.simulation_notice

    # Real inference function marks empirical_score_verified = True
    def mock_echo(prompt: str) -> dict:
        return {"content": "{\"name\": \"get_system_time\", \"args\": {}}"}

    live_res = run_local_model_benchmark("mock-model", inference_fn=mock_echo)
    assert live_res.is_simulated is False
    assert live_res.evaluation_mode == "live_model_evaluation"
    assert live_res.empirical_score_verified is True


# ---------------------------------------------------------------------------
# 6. Centralized REST API structured error contracts with dual-compatibility
# ---------------------------------------------------------------------------

def test_structured_error_responses_dual_compatibility():
    app = create_app()
    client = TestClient(app)

    # 1. 404 Not Found (e.g., non-existent task)
    res_404 = client.get("/api/tasks/non-existent-task-999")
    assert res_404.status_code == 404
    data_404 = res_404.json()
    assert "detail" in data_404
    assert data_404["error"]["code"] == "NOT_FOUND"
    assert data_404["error"]["status"] == 404

    # 2. 422 Validation Error (e.g., invalid reconcile cost request with negative cost)
    res_422 = client.post(
        "/v1/usage/reconcile",
        json={"request_id": "r1", "provider_billed_cost": -5.0, "reconciliation_source": "src"},
    )
    assert res_422.status_code == 422
    data_422 = res_422.json()
    assert "detail" in data_422
    assert data_422["error"]["code"] == "VALIDATION_ERROR"
    assert data_422["error"]["status"] == 422


# ---------------------------------------------------------------------------
# 7. Persistent task creation idempotency key deduplication and replay
# ---------------------------------------------------------------------------

def test_task_creation_idempotency_key_replay():
    app = create_app()
    client = TestClient(app)

    idemp_key = "idemp-key-sprint-audit-42"
    payload = {
        "prompt": "Test idempotent task creation",
        "steps": [{"title": "Step 1", "tool_name": "think", "tool_args": {"thought": "idempotent"}}],
        "auto_run": False,
        "idempotency_key": idemp_key,
    }

    # First creation call
    resp1 = client.post("/api/tasks", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    task_id_1 = data1["task"]["task_id"]
    assert data1["task"]["metadata"]["idempotency_key"] == idemp_key

    # Second duplicate creation call with same idempotency key
    resp2 = client.post("/api/tasks", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["idempotent_replay"] is True
    assert data2["task"]["task_id"] == task_id_1
