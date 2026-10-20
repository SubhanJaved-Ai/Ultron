"""Cancellation infrastructure for the Global Emergency Stop (GAP-01 / TSK-P5-01).

This module provides:

- ``CancellationToken``          — a lightweight event pairing ``threading.Event``
  (synchronous) with an ``asyncio.Event`` (asynchronous) so that cancellation
  signals propagate correctly in both execution modes.

- ``ActiveExecutionContextStore`` — a process-wide thread-safe registry that maps
  context IDs (strings) to their ``CancellationToken``.  Every directive execution
  must register a token before any work begins, check ``token.is_cancelled`` before
  and after every tool dispatch, and unregister the token in a ``finally`` block.

Usage pattern::

    store = get_execution_store()
    token = store.register("ctx-abc123")
    try:
        for step in steps:
            if token.is_cancelled:
                break
            run_step(step, token=token)
    finally:
        store.unregister("ctx-abc123")

Cancel from any thread or async context::

    store.cancel("ctx-abc123")        # sets the threading.Event
    await store.cancel_async("ctx-abc123")  # same, but async-safe
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass(slots=True)
class CancellationToken:
    """Dual-mode (sync + async) cancellation token for an execution context.

    Attributes:
        context_id: The unique identifier for the execution context.
        created_at: Unix timestamp (float) when this token was created.
        cancelled_at: Unix timestamp (float) when cancellation was requested,
            or ``None`` if still active.
    """

    context_id: str
    owner_session_id: Optional[str] = field(default=None)
    created_at: float = field(default_factory=time.time)
    cancelled_at: Optional[float] = field(default=None)

    # Threading event — safe to check/set from any OS thread
    _sync_event: threading.Event = field(default_factory=threading.Event)

    # asyncio Event — only touched from an event-loop context.  Created lazily
    # because event loops may not exist at construction time.
    _async_event: Optional[asyncio.Event] = field(default=None)

    # Cleanup callbacks and error tracking
    _cleanup_callbacks: list[Callable[[], Any]] = field(default_factory=list)
    _cleanup_errors: list[Exception] = field(default_factory=list)

    @property
    def is_cancelled(self) -> bool:
        """Return ``True`` if cancellation has been requested."""
        return self._sync_event.is_set()

    def add_cleanup_callback(self, callback: Callable[[], Any]) -> None:
        """Register a cleanup function to be executed when cancellation occurs.

        If the token has already been cancelled, the callback is executed immediately.
        """
        if self._sync_event.is_set():
            try:
                callback()
            except Exception as exc:
                self._cleanup_errors.append(exc)
            return
        self._cleanup_callbacks.append(callback)

    @property
    def cleanup_errors(self) -> list[Exception]:
        """Return exceptions encountered during cleanup execution."""
        return list(self._cleanup_errors)

    def cancel(self) -> None:
        """Signal cancellation from any thread.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if not self._sync_event.is_set():
            self.cancelled_at = time.time()
        self._sync_event.set()
        # Best-effort: wake up any asyncio waiters running in a loop
        if self._async_event is not None:
            try:
                self._async_event.set()
            except RuntimeError:
                # May happen if the event loop is already closed
                pass
        # Execute registered cleanup callbacks
        while self._cleanup_callbacks:
            cb = self._cleanup_callbacks.pop(0)
            try:
                cb()
            except Exception as exc:
                self._cleanup_errors.append(exc)

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until cancellation is signalled or *timeout* elapses.

        Returns:
            ``True`` if the token is now cancelled, ``False`` if the call
            timed out without a cancellation signal.
        """
        return self._sync_event.wait(timeout=timeout)

    def get_async_event(self) -> asyncio.Event:
        """Return (creating on demand) an ``asyncio.Event`` for this token.

        Must be called from within a running event loop so the event is
        bound to the correct loop on Python 3.10+.
        """
        if self._async_event is None:
            self._async_event = asyncio.Event()
            if self._sync_event.is_set():
                self._async_event.set()
        return self._async_event

    async def wait_async(self) -> None:
        """Async-native wait until cancellation is signalled."""
        event = self.get_async_event()
        await event.wait()


class ActiveExecutionContextStore:
    """Process-wide thread-safe registry of active execution contexts.

    One instance is shared across the entire FastAPI process via the module-level
    singleton ``_STORE``.  All public methods are safe to call concurrently.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._tokens: Dict[str, CancellationToken] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, context_id: str, owner_session_id: Optional[str] = None
    ) -> CancellationToken:
        """Register a new execution context and return its ``CancellationToken``.

        If a token with the same *context_id* already exists it is returned as-is
        (idempotent).

        Args:
            context_id: A unique identifier for the execution context (e.g.
                ``"ctx-<uuid>"`` or ``"active"`` for the single-user default).
            owner_session_id: Optional session identifier owning this execution.

        Returns:
            The ``CancellationToken`` bound to *context_id*.
        """
        with self._lock:
            if context_id not in self._tokens:
                self._tokens[context_id] = CancellationToken(
                    context_id=context_id,
                    owner_session_id=owner_session_id,
                )
            elif (
                owner_session_id is not None
                and self._tokens[context_id].owner_session_id is None
            ):
                self._tokens[context_id].owner_session_id = owner_session_id
            return self._tokens[context_id]

    def unregister(self, context_id: str) -> None:
        """Remove a context from the store.

        Called in ``finally`` blocks after directive execution completes or is
        cancelled.  Safe to call if the *context_id* is not registered.
        """
        with self._lock:
            self._tokens.pop(context_id, None)

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel(
        self,
        context_id: str,
        requesting_session_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> bool:
        """Signal cancellation for *context_id*.

        Args:
            context_id: The context to cancel.  If ``"active"`` is supplied and no
                context is registered under that exact key, the store cancels *all*
                currently registered contexts matching the caller's session (or all
                active contexts if the caller is an administrator).
            requesting_session_id: Optional caller session identifier used to verify
                ownership and prevent cross-session cancellation attacks.
            is_admin: Whether the caller is an authenticated administrator. If True,
                ownership restrictions are bypassed unless a specific target
                session was explicitly requested in ``requesting_session_id``.

        Returns:
            ``True`` if at least one token was cancelled, ``False`` if no matching
            context was found or if authorization failed.
        """
        with self._lock:
            if context_id in self._tokens:
                token = self._tokens[context_id]
                # Enforce strict session ownership check for non-admin callers
                if not is_admin and token.owner_session_id is not None:
                    if (
                        requesting_session_id is None
                        or token.owner_session_id != requesting_session_id
                    ):
                        return False  # Cross-session cancellation rejected
                token.cancel()
                return True

            # Broadcast cancel: "active" with no exact match → cancel tokens
            if context_id == "active" and self._tokens:
                cancelled_any = False
                for token in list(self._tokens.values()):
                    if not is_admin and token.owner_session_id is not None:
                        if (
                            requesting_session_id is None
                            or token.owner_session_id != requesting_session_id
                        ):
                            continue
                    elif (
                        is_admin
                        and requesting_session_id is not None
                        and token.owner_session_id is not None
                    ):
                        if token.owner_session_id != requesting_session_id:
                            continue
                    token.cancel()
                    cancelled_any = True
                return cancelled_any

            return False

    async def cancel_async(
        self,
        context_id: str,
        requesting_session_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> bool:
        """Async-safe cancellation signal (delegates to the sync implementation)."""
        # The synchronous path is already thread-safe; asyncio does not require
        # a separate implementation, but providing this entry point keeps caller
        # code clean in async route handlers.
        return self.cancel(
            context_id,
            requesting_session_id=requesting_session_id,
            is_admin=is_admin,
        )

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get(self, context_id: str) -> Optional[CancellationToken]:
        """Return the token for *context_id*, or ``None`` if not registered."""
        with self._lock:
            return self._tokens.get(context_id)

    def list_active(self, session_id: Optional[str] = None) -> list[str]:
        """Return a snapshot list of currently registered context IDs.

        If *session_id* is provided, only contexts owned by that session (or unowned)
        are returned to prevent cross-tenant enumeration.
        """
        with self._lock:
            if session_id is not None:
                return [
                    cid
                    for cid, tok in self._tokens.items()
                    if tok.owner_session_id is None or tok.owner_session_id == session_id
                ]
            return list(self._tokens.keys())

    def is_cancelled(self, context_id: str) -> bool:
        """Return ``True`` if the given context has been cancelled."""
        with self._lock:
            token = self._tokens.get(context_id)
            return token.is_cancelled if token is not None else False


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly
# ---------------------------------------------------------------------------

_STORE: ActiveExecutionContextStore = ActiveExecutionContextStore()


def get_execution_store() -> ActiveExecutionContextStore:
    """Return the process-wide :class:`ActiveExecutionContextStore` singleton."""
    return _STORE


__all__ = [
    "CancellationToken",
    "ActiveExecutionContextStore",
    "get_execution_store",
]
