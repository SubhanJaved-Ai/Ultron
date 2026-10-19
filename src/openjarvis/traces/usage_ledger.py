"""SQLite-backed append-only Cloud Usage & Cost Ledger.

Maintains auditable records of all cloud and local model requests, tokens,
speech characters, calculated costs, and provider-reconciled invoices.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_data_dir
from openjarvis.intelligence.pricing import PRICING_REGISTRY_VERSION, calculate_cost

logger = logging.getLogger(__name__)

_DEFAULT_LEDGER_PATH = get_data_dir() / "usage_ledger.db"

_CREATE_LEDGER_TABLE = """\
CREATE TABLE IF NOT EXISTS cloud_usage_ledger (
    request_id           TEXT PRIMARY KEY,
    task_id              TEXT NOT NULL DEFAULT '',
    agent_id             TEXT NOT NULL DEFAULT '',
    purpose              TEXT NOT NULL DEFAULT 'chat',
    provider             TEXT NOT NULL,
    model                TEXT NOT NULL,
    prompt_tokens        INTEGER NOT NULL DEFAULT 0,
    completion_tokens    INTEGER NOT NULL DEFAULT 0,
    cached_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens     INTEGER NOT NULL DEFAULT 0,
    characters           INTEGER NOT NULL DEFAULT 0,
    duration_seconds     REAL NOT NULL DEFAULT 0.0,
    cost_type            TEXT NOT NULL DEFAULT 'estimated',
    estimated_cost_usd   REAL NOT NULL DEFAULT 0.0,
    billed_cost_usd      REAL NOT NULL DEFAULT 0.0,
    pricing_version      TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'success',
    retry_count          INTEGER NOT NULL DEFAULT 0,
    metadata             TEXT NOT NULL DEFAULT '{}',
    created_at           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_created ON cloud_usage_ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_provider ON cloud_usage_ledger(provider);
CREATE INDEX IF NOT EXISTS idx_ledger_task ON cloud_usage_ledger(task_id);
"""


@dataclass
class UsageRecord:
    """Individual auditable usage event."""

    request_id: str
    provider: str
    model: str
    task_id: str = ""
    agent_id: str = ""
    purpose: str = "chat"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0
    reasoning_tokens: int = 0
    characters: int = 0
    duration_seconds: float = 0.0
    cost_type: str = "estimated"
    estimated_cost_usd: float = 0.0
    billed_cost_usd: float = 0.0
    pricing_version: str = PRICING_REGISTRY_VERSION
    status: str = "success"
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class UsageLedger:
    """Thread-safe SQLite ledger recording all inference and speech usage."""

    _instance: Optional[UsageLedger] = None
    _singleton_lock = threading.Lock()

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_LEDGER_PATH
        self._lock = threading.Lock()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: Optional[Path | str] = None) -> UsageLedger:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.executescript(_CREATE_LEDGER_TABLE)

    def record_usage(
        self,
        provider: str,
        model: str,
        *,
        request_id: Optional[str] = None,
        task_id: str = "",
        agent_id: str = "",
        purpose: str = "chat",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_prompt_tokens: int = 0,
        reasoning_tokens: int = 0,
        characters: int = 0,
        duration_seconds: float = 0.0,
        status: str = "success",
        retry_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        billed_cost_usd: float = 0.0,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> UsageRecord:
        """Calculate costs and store usage record idempotently."""
        if input_tokens is not None and prompt_tokens == 0:
            prompt_tokens = input_tokens
        if output_tokens is not None and completion_tokens == 0:
            completion_tokens = output_tokens

        req_id = request_id or str(uuid.uuid4())
        meta = metadata or {}

        # Calculate exact cost via official registry
        cost_info = calculate_cost(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            reasoning_tokens=reasoning_tokens,
            characters=characters,
        )

        cost_type = cost_info.cost_type
        if billed_cost_usd > 0.0:
            cost_type = "provider_billed"

        record = UsageRecord(
            request_id=req_id,
            task_id=task_id,
            agent_id=agent_id,
            purpose=purpose,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            reasoning_tokens=reasoning_tokens,
            characters=characters,
            duration_seconds=duration_seconds,
            cost_type=cost_type,
            estimated_cost_usd=cost_info.estimated_cost_usd,
            billed_cost_usd=billed_cost_usd,
            pricing_version=cost_info.pricing_version,
            status=status,
            retry_count=retry_count,
            metadata=meta,
            created_at=time.time(),
        )

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """\
                INSERT INTO cloud_usage_ledger (
                    request_id, task_id, agent_id, purpose, provider, model,
                    prompt_tokens, completion_tokens, cached_prompt_tokens,
                    reasoning_tokens, characters, duration_seconds, cost_type,
                    estimated_cost_usd, billed_cost_usd, pricing_version,
                    status, retry_count, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    status=excluded.status,
                    retry_count=excluded.retry_count,
                    billed_cost_usd=CASE WHEN excluded.billed_cost_usd > 0 THEN excluded.billed_cost_usd ELSE cloud_usage_ledger.billed_cost_usd END,
                    cost_type=CASE WHEN excluded.billed_cost_usd > 0 THEN 'provider_billed' ELSE cloud_usage_ledger.cost_type END
                """,
                (
                    record.request_id,
                    record.task_id,
                    record.agent_id,
                    record.purpose,
                    record.provider,
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.cached_prompt_tokens,
                    record.reasoning_tokens,
                    record.characters,
                    record.duration_seconds,
                    record.cost_type,
                    record.estimated_cost_usd,
                    record.billed_cost_usd,
                    record.pricing_version,
                    record.status,
                    record.retry_count,
                    json.dumps(record.metadata),
                    record.created_at,
                ),
            )
        return record

    def get_summary(
        self,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
        provider: Optional[str] = None,
        hours: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Aggregate usage metrics across time range and providers."""
        t_end = end_time or time.time()
        if hours is not None and hours > 0:
            start_time = max(0.0, t_end - (hours * 3600.0))
        where_clauses = ["created_at >= ?", "created_at <= ?"]
        params: List[Any] = [start_time, t_end]

        if provider:
            where_clauses.append("provider = ?")
            params.append(provider)

        where_sql = " AND ".join(where_clauses)

        with self._lock, self._get_connection() as conn:
            # Overall totals
            row = conn.execute(
                f"""\
                SELECT
                    COUNT(*) as total_requests,
                    SUM(prompt_tokens) as total_prompt_tokens,
                    SUM(completion_tokens) as total_completion_tokens,
                    SUM(cached_prompt_tokens) as total_cached_tokens,
                    SUM(reasoning_tokens) as total_reasoning_tokens,
                    SUM(characters) as total_characters,
                    SUM(estimated_cost_usd) as total_estimated_cost_usd,
                    SUM(billed_cost_usd) as total_billed_cost_usd,
                    SUM(CASE WHEN cost_type = 'local_zero' THEN 1 ELSE 0 END) as local_requests,
                    SUM(CASE WHEN cost_type = 'local_zero' THEN prompt_tokens + completion_tokens ELSE 0 END) as local_tokens,
                    SUM(CASE WHEN cost_type = 'unknown' THEN 1 ELSE 0 END) as unknown_cost_requests
                FROM cloud_usage_ledger
                WHERE {where_sql}
                """,
                params,
            ).fetchone()

            # Breakdown by provider
            provider_rows = conn.execute(
                f"""\
                SELECT
                    provider,
                    COUNT(*) as requests,
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    SUM(characters) as characters,
                    SUM(estimated_cost_usd) as estimated_cost,
                    SUM(billed_cost_usd) as billed_cost,
                    SUM(CASE WHEN cost_type = 'local_zero' THEN 1 ELSE 0 END) as is_local
                FROM cloud_usage_ledger
                WHERE {where_sql}
                GROUP BY provider
                ORDER BY estimated_cost DESC
                """,
                params,
            ).fetchall()

            # Breakdown by model
            model_rows = conn.execute(
                f"""\
                SELECT
                    provider,
                    model,
                    COUNT(*) as requests,
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    SUM(characters) as characters,
                    SUM(estimated_cost_usd) as estimated_cost,
                    SUM(billed_cost_usd) as billed_cost
                FROM cloud_usage_ledger
                WHERE {where_sql}
                GROUP BY provider, model
                ORDER BY estimated_cost DESC
                LIMIT 20
                """,
                params,
            ).fetchall()

        by_provider = [
            {
                "provider": r["provider"],
                "requests": r["requests"],
                "prompt_tokens": r["prompt_tokens"] or 0,
                "completion_tokens": r["completion_tokens"] or 0,
                "characters": r["characters"] or 0,
                "estimated_cost_usd": round(r["estimated_cost"] or 0.0, 4),
                "billed_cost_usd": round(r["billed_cost"] or 0.0, 4),
                "is_local": bool(r["is_local"]),
            }
            for r in provider_rows
        ]

        by_model = [
            {
                "provider": r["provider"],
                "model": r["model"],
                "requests": r["requests"],
                "prompt_tokens": r["prompt_tokens"] or 0,
                "completion_tokens": r["completion_tokens"] or 0,
                "characters": r["characters"] or 0,
                "estimated_cost_usd": round(r["estimated_cost"] or 0.0, 4),
                "billed_cost_usd": round(r["billed_cost"] or 0.0, 4),
            }
            for r in model_rows
        ]

        return {
            "period": {"start_time": start_time, "end_time": t_end},
            "pricing_version": PRICING_REGISTRY_VERSION,
            "total_requests": row["total_requests"] or 0,
            "total_prompt_tokens": row["total_prompt_tokens"] or 0,
            "total_completion_tokens": row["total_completion_tokens"] or 0,
            "total_cached_tokens": row["total_cached_tokens"] or 0,
            "total_reasoning_tokens": row["total_reasoning_tokens"] or 0,
            "total_characters": row["total_characters"] or 0,
            "total_estimated_cost_usd": round(row["total_estimated_cost_usd"] or 0.0, 4),
            "total_billed_cost_usd": round(row["total_billed_cost_usd"] or 0.0, 4),
            "local_requests": row["local_requests"] or 0,
            "local_tokens": row["local_tokens"] or 0,
            "unknown_cost_requests": row["unknown_cost_requests"] or 0,
            "by_provider": by_provider,
            "by_model": by_model,
        }

    def get_records(
        self,
        limit: int = 50,
        offset: int = 0,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        task_id: Optional[str] = None,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve paginated usage records with optional time range and provider filters."""
        clauses = []
        params: List[Any] = []
        if start_time > 0.0:
            clauses.append("created_at >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("created_at <= ?")
            params.append(end_time)
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if model:
            clauses.append("model = ?")
            params.append(model)
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"""\
            SELECT * FROM cloud_usage_ledger
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.get("metadata", "{}"))
            except Exception:
                d["metadata"] = {}
            result.append(d)
        return result

    def reconcile_billed_cost(
        self,
        request_id: str,
        billed_cost_usd: float,
        reconciliation_source: Optional[str] = "manual_invoice_audit",
    ) -> bool:
        """Update authoritative billed cost for a specific request with verified source provenance."""
        source_clean = str(reconciliation_source or "").strip()
        if not source_clean:
            raise ValueError(
                "Billing reconciliation requires an authoritative source or invoice reference (e.g., 'openai_invoice_2026_10')."
            )
        if billed_cost_usd < 0.0:
            raise ValueError("Billed cost cannot be negative.")

        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT metadata FROM cloud_usage_ledger WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if not row:
                return False

            try:
                meta = json.loads(row["metadata"] or "{}")
            except Exception:
                meta = {}

            meta["reconciliation_source"] = source_clean
            meta["reconciled_at"] = time.time()
            meta["reconciled_cost_usd"] = billed_cost_usd

            cursor = conn.execute(
                """\
                UPDATE cloud_usage_ledger
                SET billed_cost_usd = ?, cost_type = 'provider_billed', metadata = ?
                WHERE request_id = ?
                """,
                (billed_cost_usd, json.dumps(meta), request_id),
            )
            return cursor.rowcount > 0

    def export_csv(self, start_time: float = 0.0, end_time: Optional[float] = None) -> str:
        """Export ledger records within optional time range to CSV string."""
        records = self.get_records(
            limit=10_000,
            offset=0,
            start_time=start_time,
            end_time=end_time,
        )
        output = io.StringIO()
        fieldnames = [
            "request_id", "created_at", "provider", "model", "purpose", "task_id",
            "prompt_tokens", "completion_tokens", "cached_prompt_tokens", "reasoning_tokens",
            "characters", "duration_seconds", "cost_type", "estimated_cost_usd", "billed_cost_usd", "status"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)
        return output.getvalue()


def get_usage_ledger(db_path: Optional[Path | str] = None) -> UsageLedger:
    return UsageLedger.get_instance(db_path)
