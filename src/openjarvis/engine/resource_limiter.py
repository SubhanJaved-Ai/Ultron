"""Centralized resource limiting, concurrency control, circuit breaking, and task budgets.

Provides a unified execution boundary protecting model provider requests (OpenAI,
Anthropic, Google Gemini, Ollama, ElevenLabs, LiteLLM) across chat, tasks, and subagents.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import logging
import random
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery with single request


class ResourceLimitError(Exception):
    """Base exception for resource limiter rejections."""


class RateLimitExceededError(ResourceLimitError):
    """Raised when RPM or TPM limits are exceeded."""


class QueueFullError(ResourceLimitError):
    """Raised when backpressure queue limit is exceeded."""


class CircuitBreakerOpenError(ResourceLimitError):
    """Raised when requests are rejected due to an open circuit breaker."""


class BudgetExceededError(ResourceLimitError):
    """Raised when a task budget limit is reached."""


@dataclass
class ProviderLimitConfig:
    """Configurable limits for a specific provider or model family."""

    provider: str = ""
    requests_per_minute: int = 60
    tokens_per_minute: int = 100_000
    max_concurrent: int = 5
    max_queue_size: int = 20
    request_timeout_seconds: float = 60.0
    # Circuit breaker settings
    circuit_failure_threshold: int = 5
    circuit_cooldown_seconds: float = 30.0
    # Retry policy
    max_retries: int = 3
    initial_backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 10.0
    jitter_factor: float = 0.25
    is_local: bool = False  # Local models have concurrency control without cloud billing


@dataclass
class TaskBudgetConfig:
    """Configurable execution budget per task or request workflow."""

    max_model_calls: Optional[int] = 50
    max_tokens: Optional[int] = 200_000
    max_spend_usd: Optional[float] = 5.00
    max_duration_seconds: Optional[float] = 300.0


@dataclass
class TaskBudgetUsage:
    """Observed usage against a task budget."""

    task_id: str
    model_calls: int = 0
    total_tokens: int = 0
    estimated_spend_usd: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    completed: bool = False


class TokenBucket:
    """Thread-safe token bucket for rate and token limiting."""

    def __init__(self, rate_per_second: float, capacity: float) -> None:
        self.rate = rate_per_second
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> Tuple[bool, float]:
        """Attempt to consume tokens. Returns (success, wait_seconds)."""
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= amount:
                self.tokens -= amount
                return True, 0.0
            else:
                wait_time = (amount - self.tokens) / self.rate if self.rate > 0 else 1.0
                return False, max(0.0, wait_time)

    def current_tokens(self) -> float:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            return min(self.capacity, self.tokens + elapsed * self.rate)


class CircuitBreaker:
    """Circuit breaker guarding against cascading provider failures."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.opened_at = 0.0
        self.last_error_message = ""
        self.lock = threading.Lock()

    def can_execute(self) -> bool:
        with self.lock:
            now = time.monotonic()
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if now - self.opened_at >= self.cooldown_seconds:
                    logger.info("Circuit breaker entering HALF_OPEN probe state")
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            # In HALF_OPEN, allow single test call
            return True

    def record_success(self) -> None:
        with self.lock:
            self.consecutive_failures = 0
            if self.state != CircuitState.CLOSED:
                logger.info("Circuit breaker closed after successful recovery call")
                self.state = CircuitState.CLOSED
                self.last_error_message = ""

    def record_failure(self, error_message: str = "") -> None:
        with self.lock:
            self.consecutive_failures += 1
            self.last_error_message = error_message
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                logger.warning("Circuit breaker re-opened on probe failure: %s", error_message)
            elif self.consecutive_failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker tripped to OPEN after %d consecutive failures: %s",
                    self.consecutive_failures,
                    error_message,
                )

    def reset(self) -> None:
        with self.lock:
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
            self.opened_at = 0.0
            self.last_error_message = ""

    def cooldown_remaining(self) -> float:
        with self.lock:
            if self.state != CircuitState.OPEN:
                return 0.0
            elapsed = time.monotonic() - self.opened_at
            remaining = self.cooldown_seconds - elapsed
            return max(0.0, remaining)


class ProviderLimiter:
    """Manages rate-limits, concurrency, and circuit breakers for a provider."""

    def __init__(self, provider: str, config: Optional[ProviderLimitConfig] = None) -> None:
        self.provider = provider
        self.config = config or ProviderLimitConfig()
        self._req_bucket = TokenBucket(
            rate_per_second=self.config.requests_per_minute / 60.0,
            capacity=float(self.config.requests_per_minute),
        )
        self._tok_bucket = TokenBucket(
            rate_per_second=self.config.tokens_per_minute / 60.0,
            capacity=float(self.config.tokens_per_minute),
        )
        self._active_concurrency = 0
        self._queue_length = 0
        self._lock = threading.Lock()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_failure_threshold,
            cooldown_seconds=self.config.circuit_cooldown_seconds,
        )

    def update_config(self, **kwargs: Any) -> None:
        """Update provider limits dynamically."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self.config, k) and v is not None:
                    setattr(self.config, k, v)
            # Recreate buckets with new rates
            self._req_bucket = TokenBucket(
                rate_per_second=self.config.requests_per_minute / 60.0,
                capacity=float(self.config.requests_per_minute),
            )
            self._tok_bucket = TokenBucket(
                rate_per_second=self.config.tokens_per_minute / 60.0,
                capacity=float(self.config.tokens_per_minute),
            )
            self.circuit_breaker.failure_threshold = self.config.circuit_failure_threshold
            self.circuit_breaker.cooldown_seconds = self.config.circuit_cooldown_seconds

    def check_and_acquire(self, estimated_tokens: int = 100) -> None:
        """Pre-flight check and acquire slot. Raises ResourceLimitError on breach."""
        if not self.circuit_breaker.can_execute():
            remaining = max(0.0, self.circuit_breaker.cooldown_seconds - (time.monotonic() - self.circuit_breaker.opened_at))
            raise CircuitBreakerOpenError(
                f"Circuit breaker for provider '{self.provider}' is OPEN due to repeated failures. "
                f"Cooldown active for {remaining:.1f}s. Last error: {self.circuit_breaker.last_error_message}"
            )

        with self._lock:
            if self._active_concurrency >= self.config.max_concurrent:
                if self._queue_length >= self.config.max_queue_size:
                    raise QueueFullError(
                        f"Provider '{self.provider}' queue is full ({self._queue_length}/{self.config.max_queue_size}). Backpressure applied."
                    )
                # Check concurrency rejection if not queuing
                raise ResourceLimitError(
                    f"Provider '{self.provider}' reached max concurrent requests ({self.config.max_concurrent})."
                )

        # Check RPM
        allowed, wait_sec = self._req_bucket.consume(1.0)
        if not allowed:
            raise RateLimitExceededError(
                f"Provider '{self.provider}' exceeded requests-per-minute limit ({self.config.requests_per_minute} RPM). "
                f"Retry in {wait_sec:.2f}s."
            )

        # Check TPM (if positive)
        if estimated_tokens > 0:
            tok_allowed, tok_wait = self._tok_bucket.consume(float(estimated_tokens))
            if not tok_allowed:
                raise RateLimitExceededError(
                    f"Provider '{self.provider}' exceeded tokens-per-minute limit ({self.config.tokens_per_minute} TPM). "
                    f"Retry in {tok_wait:.2f}s."
                )

        with self._lock:
            self._active_concurrency += 1

    def release(self, success: bool = True, error_message: str = "") -> None:
        """Release concurrency slot and update circuit breaker."""
        with self._lock:
            self._active_concurrency = max(0, self._active_concurrency - 1)
        if success:
            self.circuit_breaker.record_success()
        else:
            self.circuit_breaker.record_failure(error_message)

    def status(self) -> Dict[str, Any]:
        """Return diagnostic status of this provider limiter."""
        with self._lock:
            cfg_dict = asdict(self.config)
            return {
                "provider": self.provider,
                "config": cfg_dict,
                "is_local": self.config.is_local,
                "requests_per_minute_limit": self.config.requests_per_minute,
                "tokens_per_minute_limit": self.config.tokens_per_minute,
                "max_concurrency": self.config.max_concurrent,
                "request_timeout_seconds": self.config.request_timeout_seconds,
                "active_concurrency": self._active_concurrency,
                "available_req_tokens": round(self._req_bucket.current_tokens(), 2),
                "available_tok_tokens": round(self._tok_bucket.current_tokens(), 2),
                "circuit_state": self.circuit_breaker.state.value,
                "circuit_consecutive_failures": self.circuit_breaker.consecutive_failures,
                "circuit_cooldown_remaining_seconds": max(0.0, self.circuit_breaker.cooldown_remaining()),
                "circuit_last_error": self.circuit_breaker.last_error_message,
            }


class CentralizedResourceLimiter:
    """Global manager for rate-limits, concurrency, circuit breakers, and budgets."""

    _instance: Optional[CentralizedResourceLimiter] = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderLimiter] = {}
        self._task_budgets: Dict[str, TaskBudgetUsage] = {}
        self._default_task_budget = TaskBudgetConfig()
        self._lock = threading.Lock()
        self._init_default_providers()

    @classmethod
    def get_instance(cls) -> CentralizedResourceLimiter:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _init_default_providers(self) -> None:
        # Defaults for well-known providers
        defaults: Dict[str, ProviderLimitConfig] = {
            "openai": ProviderLimitConfig(requests_per_minute=120, tokens_per_minute=200_000, max_concurrent=10),
            "anthropic": ProviderLimitConfig(requests_per_minute=60, tokens_per_minute=100_000, max_concurrent=5),
            "google": ProviderLimitConfig(requests_per_minute=120, tokens_per_minute=500_000, max_concurrent=10),
            "gemini": ProviderLimitConfig(requests_per_minute=120, tokens_per_minute=500_000, max_concurrent=10),
            "elevenlabs": ProviderLimitConfig(requests_per_minute=30, tokens_per_minute=50_000, max_concurrent=3),
            "ollama": ProviderLimitConfig(requests_per_minute=600, tokens_per_minute=1_000_000, max_concurrent=4, is_local=True),
            "default": ProviderLimitConfig(requests_per_minute=60, tokens_per_minute=100_000, max_concurrent=5),
        }
        for name, cfg in defaults.items():
            self._providers[name] = ProviderLimiter(name, cfg)

    def get_limiter(self, provider: str) -> ProviderLimiter:
        norm = (provider or "default").lower().split("-")[0].split("/")[0]
        with self._lock:
            if norm not in self._providers:
                # Inherit from default config
                cfg = ProviderLimitConfig()
                self._providers[norm] = ProviderLimiter(norm, cfg)
            return self._providers[norm]

    # --- Task Budget Management ---

    def register_task(self, task_id: str, custom_budget: Optional[TaskBudgetConfig] = None) -> TaskBudgetUsage:
        """Register a new task with its execution budget."""
        with self._lock:
            usage = TaskBudgetUsage(task_id=task_id)
            self._task_budgets[task_id] = usage
            return usage

    def get_task_usage(self, task_id: str) -> Optional[TaskBudgetUsage]:
        with self._lock:
            return self._task_budgets.get(task_id)

    def check_task_budget(
        self,
        task_id: str,
        budget_config: Optional[TaskBudgetConfig] = None,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        allow_unmetered_on_spend_budget: bool = False,
    ) -> None:
        """Validate that task has not exceeded its budget limits."""
        if not task_id:
            return
        budget = budget_config or self._default_task_budget
        with self._lock:
            usage = self._task_budgets.get(task_id)
            if not usage:
                usage = TaskBudgetUsage(task_id=task_id)
                self._task_budgets[task_id] = usage

            now = time.monotonic()
            duration = now - usage.started_at

            if budget.max_model_calls is not None and usage.model_calls >= budget.max_model_calls:
                raise BudgetExceededError(
                    f"Task '{task_id}' exceeded model call budget ({usage.model_calls}/{budget.max_model_calls} calls)."
                )

            if budget.max_tokens is not None and usage.total_tokens >= budget.max_tokens:
                raise BudgetExceededError(
                    f"Task '{task_id}' exceeded token budget ({usage.total_tokens}/{budget.max_tokens} tokens)."
                )

            if budget.max_spend_usd is not None and usage.estimated_spend_usd >= budget.max_spend_usd:
                raise BudgetExceededError(
                    f"Task '{task_id}' exceeded cloud spend budget (${usage.estimated_spend_usd:.4f}/${budget.max_spend_usd:.2f})."
                )

            # Prevent uncataloged / unknown-priced models from silently bypassing a hard spend budget
            if budget.max_spend_usd is not None and model and not allow_unmetered_on_spend_budget:
                norm_prov = (provider or "").lower()
                if norm_prov not in ("ollama", "local"):
                    from openjarvis.intelligence.pricing import resolve_price_entry
                    if resolve_price_entry(norm_prov or "default", model) is None:
                        raise BudgetExceededError(
                            f"Task '{task_id}' has a hard spend budget (${budget.max_spend_usd:.2f}), "
                            f"but model '{model}' has uncataloged/unknown pricing. "
                            f"Operation blocked to prevent unmetered spend bypass."
                        )

            if budget.max_duration_seconds is not None and duration >= budget.max_duration_seconds:
                raise BudgetExceededError(
                    f"Task '{task_id}' exceeded maximum duration budget ({duration:.1f}s/{budget.max_duration_seconds:.1f}s)."
                )

    def record_task_consumption(
        self,
        task_id: str,
        tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        """Record model call and token consumption for a task."""
        if not task_id:
            return
        with self._lock:
            usage = self._task_budgets.get(task_id)
            if not usage:
                usage = TaskBudgetUsage(task_id=task_id)
                self._task_budgets[task_id] = usage
            usage.model_calls += 1
            usage.total_tokens += tokens
            usage.estimated_spend_usd += estimated_cost_usd

    # --- Execution Wrapper with Bounded Retries & Backoff ---

    def execute_with_policy(
        self,
        provider: str,
        call_fn: Callable[[], Any],
        *,
        model: str = "",
        estimated_tokens: int = 100,
        task_id: str = "",
        is_idempotent: bool = True,
    ) -> Any:
        """Execute a provider call wrapped in rate-limiting, concurrency, retry, and budget controls."""
        limiter = self.get_limiter(provider)
        cfg = limiter.config

        # Check task budget first
        self.check_task_budget(task_id, model=model, provider=provider)

        last_exc: Optional[Exception] = None
        attempt = 0

        while attempt <= cfg.max_retries:
            attempt += 1
            limiter.check_and_acquire(estimated_tokens=estimated_tokens)
            try:
                result = call_fn()
                limiter.release(success=True)
                return result
            except Exception as exc:
                err_msg = str(exc)
                limiter.release(success=False, error_message=err_msg)
                last_exc = exc

                # Do NOT retry authentication failures (401/403)
                if any(code in err_msg for code in ("401", "403", "unauthorized", "invalid_api_key", "Forbidden")):
                    logger.error("Authentication error calling %s; not retrying: %s", provider, err_msg)
                    raise

                # Do NOT retry non-idempotent actions
                if not is_idempotent:
                    logger.warning("Call to %s is not marked idempotent; failing fast: %s", provider, err_msg)
                    raise

                # Check if we have retries left
                if attempt > cfg.max_retries:
                    break

                # Calculate backoff with jitter or Retry-After
                backoff = min(
                    cfg.max_backoff_seconds,
                    cfg.initial_backoff_seconds * (cfg.backoff_multiplier ** (attempt - 1)),
                )
                jitter = backoff * cfg.jitter_factor * (random.random() * 2 - 1)
                sleep_time = max(0.1, backoff + jitter)

                # Honor Retry-After header if present
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None and isinstance(retry_after, (int, float)):
                    sleep_time = min(cfg.max_backoff_seconds, float(retry_after))

                logger.warning(
                    "Call to %s failed (attempt %d/%d): %s. Backing off for %.2fs.",
                    provider,
                    attempt,
                    cfg.max_retries + 1,
                    err_msg,
                    sleep_time,
                )
                time.sleep(sleep_time)

        if last_exc:
            raise last_exc
        raise ResourceLimitError(f"Execution failed for provider '{provider}' after {cfg.max_retries} retries.")

    async def execute_with_policy_async(
        self,
        provider: str,
        coro_fn: Callable[[], Any],
        *,
        model: str = "",
        estimated_tokens: int = 100,
        task_id: str = "",
        is_idempotent: bool = True,
    ) -> Any:
        """Asynchronously execute a provider call wrapped in rate-limiting, concurrency, retry, and budget controls."""
        limiter = self.get_limiter(provider)
        cfg = limiter.config

        # Check task budget first
        self.check_task_budget(task_id, model=model, provider=provider)

        last_exc: Optional[Exception] = None
        attempt = 0

        while attempt <= cfg.max_retries:
            attempt += 1
            limiter.check_and_acquire(estimated_tokens=estimated_tokens)
            try:
                res = coro_fn()
                if asyncio.iscoroutine(res):
                    result = await res
                else:
                    result = res
                limiter.release(success=True)
                return result
            except Exception as exc:
                err_msg = str(exc)
                limiter.release(success=False, error_message=err_msg)
                last_exc = exc

                # Do NOT retry authentication failures (401/403)
                if any(code in err_msg for code in ("401", "403", "unauthorized", "invalid_api_key", "Forbidden")):
                    logger.error("Authentication error calling %s; not retrying: %s", provider, err_msg)
                    raise

                # Do NOT retry non-idempotent actions
                if not is_idempotent:
                    logger.warning("Call to %s is not marked idempotent; failing fast: %s", provider, err_msg)
                    raise

                # Check if we have retries left
                if attempt > cfg.max_retries:
                    break

                backoff = min(
                    cfg.max_backoff_seconds,
                    cfg.initial_backoff_seconds * (cfg.backoff_multiplier ** (attempt - 1)),
                )
                jitter = backoff * cfg.jitter_factor * (random.random() * 2 - 1)
                sleep_time = max(0.1, backoff + jitter)

                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None and isinstance(retry_after, (int, float)):
                    sleep_time = min(cfg.max_backoff_seconds, float(retry_after))

                logger.warning(
                    "Async call to %s failed (attempt %d/%d): %s. Backing off for %.2fs.",
                    provider,
                    attempt,
                    cfg.max_retries + 1,
                    err_msg,
                    sleep_time,
                )
                await asyncio.sleep(sleep_time)

        if last_exc:
            raise last_exc
        raise ResourceLimitError(f"Execution failed for provider '{provider}' after {cfg.max_retries} retries.")

    @asynccontextmanager
    async def acquire_slot(
        self,
        provider: str,
        estimated_tokens: int = 100,
        task_id: str = "",
        model: str = "",
        allow_unmetered_on_spend_budget: bool = False,
    ) -> AsyncIterator[ProviderLimiter]:
        """Async context manager acquiring concurrency, rate token, and task budget slot."""
        limiter = self.get_limiter(provider)
        self.check_task_budget(
            task_id,
            model=model,
            provider=provider,
            allow_unmetered_on_spend_budget=allow_unmetered_on_spend_budget,
        )
        limiter.check_and_acquire(estimated_tokens=estimated_tokens)
        success = False
        error_message = ""
        try:
            yield limiter
            success = True
        except Exception as exc:
            error_message = str(exc)
            raise
        finally:
            limiter.release(success=success, error_message=error_message)

    @contextmanager
    def acquire_slot_sync(
        self,
        provider: str,
        estimated_tokens: int = 100,
        task_id: str = "",
        model: str = "",
        allow_unmetered_on_spend_budget: bool = False,
    ) -> Iterator[ProviderLimiter]:
        """Sync context manager acquiring concurrency, rate token, and task budget slot."""
        limiter = self.get_limiter(provider)
        self.check_task_budget(
            task_id,
            model=model,
            provider=provider,
            allow_unmetered_on_spend_budget=allow_unmetered_on_spend_budget,
        )
        limiter.check_and_acquire(estimated_tokens=estimated_tokens)
        success = False
        error_message = ""
        try:
            yield limiter
            success = True
        except Exception as exc:
            error_message = str(exc)
            raise
        finally:
            limiter.release(success=success, error_message=error_message)

    def summary(self) -> Dict[str, Any]:
        """Diagnostic summary of all configured providers and task budgets."""
        with self._lock:
            return {
                "providers": {name: p.status() for name, p in self._providers.items()},
                "default_task_budget": asdict(self._default_task_budget),
                "active_task_count": len(self._task_budgets),
            }

    def get_config(self, provider: str) -> ProviderLimitConfig:
        limiter = self.get_limiter(provider)
        cfg = limiter.config
        cfg.provider = provider
        return cfg

    def set_config(self, cfg: ProviderLimitConfig) -> None:
        prov_name = cfg.provider or "default"
        norm = prov_name.lower().split("-")[0].split("/")[0]
        with self._lock:
            self._providers[norm] = ProviderLimiter(norm, cfg)

    def get_all_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {name: p.status() for name, p in self._providers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers and counters."""
        with self._lock:
            for p in self._providers.values():
                p.circuit_breaker.reset()
                p._active_concurrency = 0


def get_resource_limiter() -> CentralizedResourceLimiter:
    return CentralizedResourceLimiter.get_instance()


# Convenient aliases
get_provider_limiter = get_resource_limiter
ProviderConfig = ProviderLimitConfig
