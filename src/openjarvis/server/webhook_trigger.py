"""Webhook trigger registry for inbound event-driven automations.

Allows external systems (GitHub, Stripe, custom webhooks, n8n, cURL) to trigger
OpenJarvis workflows or agent prompts on inbound HTTP POST requests.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)


@dataclass
class WebhookTrigger:
    """Registered inbound webhook trigger definition."""

    slug: str
    target_type: str  # "workflow" | "prompt"
    target_name: str  # workflow name or prompt template
    secret_token: str = ""
    description: str = ""
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WebhookTriggerRegistry:
    """SQLite-backed registry for inbound webhook automation triggers."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            db_path = get_config_dir() / "webhook_triggers.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS webhook_triggers (
                slug         TEXT PRIMARY KEY,
                target_type  TEXT NOT NULL,
                target_name  TEXT NOT NULL,
                secret_token TEXT DEFAULT '',
                description  TEXT DEFAULT '',
                created_at   REAL
            );
        """)
        self._conn.commit()

    def register(
        self,
        slug: str,
        target_type: str,
        target_name: str,
        *,
        secret_token: str = "",
        description: str = "",
    ) -> WebhookTrigger:
        """Register or update an inbound webhook trigger."""
        now = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO webhook_triggers
                (slug, target_type, target_name, secret_token, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (slug, target_type, target_name, secret_token, description, now),
        )
        self._conn.commit()
        return WebhookTrigger(
            slug=slug,
            target_type=target_type,
            target_name=target_name,
            secret_token=secret_token,
            description=description,
            created_at=now,
        )

    def get(self, slug: str) -> Optional[WebhookTrigger]:
        """Fetch trigger by slug."""
        row = self._conn.execute(
            "SELECT * FROM webhook_triggers WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not row:
            return None
        return WebhookTrigger(
            slug=row["slug"],
            target_type=row["target_type"],
            target_name=row["target_name"],
            secret_token=row["secret_token"] or "",
            description=row["description"] or "",
            created_at=row["created_at"] or 0.0,
        )

    def list_all(self) -> List[WebhookTrigger]:
        """List all active webhook triggers."""
        rows = self._conn.execute(
            "SELECT * FROM webhook_triggers ORDER BY created_at DESC"
        ).fetchall()
        return [
            WebhookTrigger(
                slug=r["slug"],
                target_type=r["target_type"],
                target_name=r["target_name"],
                secret_token=r["secret_token"] or "",
                description=r["description"] or "",
                created_at=r["created_at"] or 0.0,
            )
            for r in rows
        ]

    def delete(self, slug: str) -> bool:
        """Delete trigger by slug."""
        cur = self._conn.execute("DELETE FROM webhook_triggers WHERE slug = ?", (slug,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
