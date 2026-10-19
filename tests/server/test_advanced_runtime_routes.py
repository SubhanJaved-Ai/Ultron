"""Tests for advanced runtime, usage ledger, and local model wizard routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server.api_routes import include_all_routes
from openjarvis.traces.usage_ledger import get_usage_ledger


@pytest.fixture
def client(tmp_path, monkeypatch):
    from openjarvis.traces.usage_ledger import UsageLedger
    test_db = tmp_path / "test_api_usage.db"
    test_ledger = UsageLedger(test_db)
    monkeypatch.setattr(UsageLedger, "_instance", test_ledger)
    import openjarvis.traces.usage_ledger as ul_mod
    monkeypatch.setattr(ul_mod, "get_usage_ledger", lambda db_path=None: test_ledger)

    app = FastAPI()
    include_all_routes(app)
    return TestClient(app)


class TestRuntimeRoutes:
    def test_get_runtime_limits(self, client):
        resp = client.get("/v1/runtime/limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "providers" in data
        assert "openai" in data["providers"]
        assert "ollama" in data["providers"]

    def test_update_runtime_limits(self, client):
        resp = client.post(
            "/v1/runtime/limits",
            json={
                "provider": "anthropic",
                "requests_per_minute": 150,
                "max_concurrency": 8,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["config"]["requests_per_minute"] == 150
        assert data["config"]["max_concurrency"] == 8

    def test_reset_runtime_limits(self, client):
        resp = client.post("/v1/runtime/limits/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reset"
        assert "providers" in data


class TestUsageRoutes:
    def test_get_usage_summary_empty(self, client):
        resp = client.get("/v1/usage/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 0
        assert data["total_estimated_cost_usd"] == 0.0
        assert "pricing_version" in data

    def test_usage_records_and_export(self, client, tmp_path):
        from openjarvis.traces.usage_ledger import get_usage_ledger

        ledger = get_usage_ledger()
        ledger.record_usage(
            request_id="req-route-test-1",
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=200,
        )

        # GET /v1/usage/summary
        resp_sum = client.get("/v1/usage/summary")
        assert resp_sum.status_code == 200
        sum_data = resp_sum.json()
        assert sum_data["total_requests"] == 1
        assert sum_data["total_estimated_cost_usd"] > 0

        # GET /v1/usage/ledger
        resp_ledger = client.get("/v1/usage/ledger?limit=10")
        assert resp_ledger.status_code == 200
        ledger_data = resp_ledger.json()
        assert ledger_data["count"] == 1
        assert ledger_data["records"][0]["request_id"] == "req-route-test-1"

        # GET /v1/usage/export
        resp_export = client.get("/v1/usage/export")
        assert resp_export.status_code == 200
        assert "text/csv" in resp_export.headers.get("content-type", "")
        assert "req-route-test-1" in resp_export.text

    def test_reconcile_usage_cost(self, client):
        from openjarvis.traces.usage_ledger import get_usage_ledger

        ledger = get_usage_ledger()
        ledger.record_usage(
            request_id="req-reconcile-target",
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=200,
        )

        resp = client.post(
            "/v1/usage/reconcile",
            json={
                "request_id": "req-reconcile-target",
                "provider_billed_cost": 0.0055,
                "reconciliation_source": "test_invoice",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reconciled"

        # 404 for non-existent request
        resp_404 = client.post(
            "/v1/usage/reconcile",
            json={
                "request_id": "non-existent-req",
                "provider_billed_cost": 1.0,
            },
        )
        assert resp_404.status_code == 404


class TestWizardRoutes:
    def test_get_hardware(self, client):
        resp = client.get("/v1/wizard/hardware")
        assert resp.status_code == 200
        data = resp.json()
        assert "platform_os" in data
        assert "cpu_cores" in data
        assert "total_ram_gb" in data

    def test_get_recommendations(self, client):
        resp = client.get("/v1/wizard/recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert "hardware" in data
        assert "recommendations" in data
        assert len(data["recommendations"]) > 0
        rec = data["recommendations"][0]
        assert "model_id" in rec
        assert "overall_score" in rec
        assert "category" in rec

    def test_run_benchmark(self, client):
        resp = client.post(
            "/v1/wizard/benchmark",
            json={"model_id": "qwen2.5:7b"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_id"] == "qwen2.5:7b"
        assert data["scenarios_tested"] == 8
        assert "pass_rate_pct" in data

    def test_install_requires_confirmation(self, client):
        # Confirmation not provided -> 400
        resp = client.post(
            "/v1/wizard/install",
            json={"model_id": "qwen2.5:7b", "confirm": False},
        )
        assert resp.status_code == 400
        assert "confirmation required" in resp.json()["detail"].lower()

    def test_model_preference_configure_and_rollback(self, client):
        # Current
        curr = client.get("/v1/wizard/current").json()
        assert "current" in curr

        # Configure initial
        resp_cfg1 = client.post(
            "/v1/wizard/configure",
            json={"provider": "ollama", "model": "qwen3:4b"},
        )
        assert resp_cfg1.status_code == 200

        # Configure new selection
        resp_cfg2 = client.post(
            "/v1/wizard/configure",
            json={"provider": "ollama", "model": "qwen3:8b"},
        )
        assert resp_cfg2.status_code == 200
        assert resp_cfg2.json()["current"]["model"] == "qwen3:8b"

        # Rollback to previous
        resp_rb = client.post("/v1/wizard/rollback")
        assert resp_rb.status_code == 200
        assert resp_rb.json()["status"] == "rolled_back"
        assert resp_rb.json()["current"]["model"] == "qwen3:4b"
