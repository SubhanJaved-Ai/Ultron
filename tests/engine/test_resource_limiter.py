"""Tests for centralized resource limiting, concurrency control, circuit breaking, and task budgets."""

from __future__ import annotations

import time
import pytest

from openjarvis.engine.resource_limiter import (
    BudgetExceededError,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    CentralizedResourceLimiter,
    ProviderLimitConfig,
    ProviderLimiter,
    QueueFullError,
    RateLimitExceededError,
    ResourceLimitError,
    TaskBudgetConfig,
    TokenBucket,
    get_resource_limiter,
)


def test_token_bucket_consume_and_refill() -> None:
    # 60 tokens per second, capacity 60
    bucket = TokenBucket(rate_per_second=60.0, capacity=60.0)
    assert bucket.current_tokens() >= 59.9

    # Consume 60
    allowed, wait = bucket.consume(60.0)
    assert allowed is True
    assert wait == 0.0

    # Next immediate consume should fail
    allowed, wait = bucket.consume(1.0)
    assert allowed is False
    assert wait > 0.0


def test_provider_limiter_rpm_enforcement() -> None:
    cfg = ProviderLimitConfig(requests_per_minute=2, tokens_per_minute=1000, max_concurrent=5)
    limiter = ProviderLimiter("test_provider", cfg)

    # 1st call
    limiter.check_and_acquire(estimated_tokens=10)
    limiter.release(success=True)

    # 2nd call
    limiter.check_and_acquire(estimated_tokens=10)
    limiter.release(success=True)

    # 3rd call should trigger RateLimitExceededError
    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check_and_acquire(estimated_tokens=10)
    assert "requests-per-minute limit" in str(exc_info.value)


def test_provider_limiter_concurrency_limit() -> None:
    cfg = ProviderLimitConfig(requests_per_minute=100, tokens_per_minute=100_000, max_concurrent=2)
    limiter = ProviderLimiter("test_concurrency", cfg)

    limiter.check_and_acquire()
    limiter.check_and_acquire()

    # 3rd concurrent request without release should fail
    with pytest.raises(ResourceLimitError) as exc_info:
        limiter.check_and_acquire()
    assert "reached max concurrent requests" in str(exc_info.value)

    # Release one, then acquiring should succeed
    limiter.release(success=True)
    limiter.check_and_acquire()
    limiter.release(success=True)
    limiter.release(success=True)


def test_circuit_breaker_transitions() -> None:
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.2)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 1st and 2nd failure
    cb.record_failure("error 1")
    cb.record_failure("error 2")
    assert cb.state == CircuitState.CLOSED

    # 3rd failure trips the breaker
    cb.record_failure("error 3")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # During cooldown, can_execute is False
    assert cb.can_execute() is False

    # Wait for cooldown
    time.sleep(0.25)
    # Should transition to HALF_OPEN probe
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Success in HALF_OPEN resets breaker to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.consecutive_failures == 0


def test_circuit_breaker_half_open_failure_reopens() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
    cb.record_failure("err 1")
    cb.record_failure("err 2")
    assert cb.state == CircuitState.OPEN

    time.sleep(0.12)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Failure during HALF_OPEN should immediately re-open
    cb.record_failure("still failing")
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


def test_execute_with_policy_no_retry_on_auth_error() -> None:
    limiter = CentralizedResourceLimiter()
    call_count = 0

    def fail_auth():
        nonlocal call_count
        call_count += 1
        raise ValueError("HTTP 401 Unauthorized: invalid_api_key")

    with pytest.raises(ValueError) as exc_info:
        limiter.execute_with_policy("openai", fail_auth)

    assert "401 Unauthorized" in str(exc_info.value)
    # Exactly 1 attempt — must NOT retry auth errors!
    assert call_count == 1


def test_execute_with_policy_no_retry_on_non_idempotent() -> None:
    limiter = CentralizedResourceLimiter()
    call_count = 0

    def fail_action():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Transient connection reset")

    with pytest.raises(RuntimeError):
        limiter.execute_with_policy("anthropic", fail_action, is_idempotent=False)

    # Non-idempotent action must fail fast without retry
    assert call_count == 1


def test_execute_with_policy_retries_transient_error() -> None:
    limiter = CentralizedResourceLimiter()
    # Configure fast backoff for test
    limiter.get_limiter("google").update_config(
        max_retries=2,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
    )
    call_count = 0

    def fail_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("Temporary 503 Service Unavailable")
        return "success_result"

    result = limiter.execute_with_policy("google", fail_then_succeed, is_idempotent=True)
    assert result == "success_result"
    assert call_count == 2


def test_task_budget_enforcement() -> None:
    limiter = CentralizedResourceLimiter()
    task_id = "task-budget-test-1"
    budget = TaskBudgetConfig(max_model_calls=3, max_tokens=500, max_spend_usd=0.05)

    limiter.register_task(task_id)

    # Call 1 & 2
    limiter.check_task_budget(task_id, budget)
    limiter.record_task_consumption(task_id, tokens=200, estimated_cost_usd=0.01)

    limiter.check_task_budget(task_id, budget)
    limiter.record_task_consumption(task_id, tokens=200, estimated_cost_usd=0.01)

    # Call 3 reaches call limit (3 calls)
    limiter.check_task_budget(task_id, budget)
    limiter.record_task_consumption(task_id, tokens=150, estimated_cost_usd=0.01)

    # 4th check should exceed call limit
    with pytest.raises(BudgetExceededError) as exc_info:
        limiter.check_task_budget(task_id, budget)
    assert "exceeded model call budget" in str(exc_info.value)


def test_task_budget_token_limit() -> None:
    limiter = CentralizedResourceLimiter()
    task_id = "task-token-budget"
    budget = TaskBudgetConfig(max_model_calls=100, max_tokens=1000)

    limiter.record_task_consumption(task_id, tokens=1200)
    with pytest.raises(BudgetExceededError) as exc_info:
        limiter.check_task_budget(task_id, budget)
    assert "exceeded token budget" in str(exc_info.value)


def test_task_budget_spend_limit() -> None:
    limiter = CentralizedResourceLimiter()
    task_id = "task-spend-budget"
    budget = TaskBudgetConfig(max_spend_usd=1.00)

    limiter.record_task_consumption(task_id, tokens=5000, estimated_cost_usd=1.50)
    with pytest.raises(BudgetExceededError) as exc_info:
        limiter.check_task_budget(task_id, budget)
    assert "exceeded cloud spend budget" in str(exc_info.value)


def test_local_model_limiter_configuration() -> None:
    limiter = CentralizedResourceLimiter()
    ollama_lim = limiter.get_limiter("ollama")
    assert ollama_lim.config.is_local is True
    # Has concurrency control
    assert ollama_lim.config.max_concurrent > 0
    # Summary contains diagnostic info
    summary = limiter.summary()
    assert "ollama" in summary["providers"]
    assert summary["providers"]["ollama"]["config"]["is_local"] is True
