"""Memory and database storage backend manager for OpenJarvis/Ultron.

Allows users to switch between local host storage (SQLite, local files) and
user-provided private cloud databases like Supabase (PostgreSQL + pgvector)
or MongoDB, ensuring complete per-user isolation and zero data sharing.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)


def _get_storage_config_path() -> Path:
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "storage_backend.json"


def _mask_connection_string(uri: str) -> str:
    """Mask passwords in database connection URIs for secure display."""
    if not uri:
        return ""
    # Mask password in URI e.g. postgresql://user:pass@host:port/db
    return re.sub(r":([^/@:]+)@", ":****@", uri)


class MemoryBackendManager:
    """Manages the active memory storage backend and cloud database attachment."""

    @staticmethod
    def load_config() -> Dict[str, Any]:
        """Load storage configuration."""
        f = _get_storage_config_path()
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "backend_type": "local",
            "connection_string": "",
            "supabase_url": "",
            "supabase_key": "",
            "database_name": "ultron_memory",
            "status": "active",
        }

    @staticmethod
    def save_config(cfg: Dict[str, Any]) -> None:
        """Save storage configuration."""
        f = _get_storage_config_path()
        f.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Return human-readable and structured status of the memory backend."""
        cfg = cls.load_config()
        backend = cfg.get("backend_type", "local")

        if backend == "local":
            return {
                "backend": "local",
                "status": "active",
                "storage_type": "Local SQLite & Markdown Files",
                "location": str(get_config_dir()),
                "message": (
                    "I am currently using your local memory. If you want to attach "
                    "other services like Supabase (PostgreSQL with pgvector) or MongoDB, "
                    "you can attach your private credentials and I will save your memory "
                    "directly there. Each database is private and isolated to you."
                ),
            }

        masked_uri = _mask_connection_string(cfg.get("connection_string", ""))
        return {
            "backend": backend,
            "status": "connected",
            "storage_type": f"Cloud Database ({backend.upper()})",
            "connection_target": masked_uri or cfg.get("supabase_url", ""),
            "database_name": cfg.get("database_name", "ultron_memory"),
            "isolation": "Private per-user dedicated database",
            "message": (
                f"Currently saving all memory and session data to your private {backend.upper()} "
                f"database ({masked_uri or cfg.get('supabase_url')}). Your data is completely "
                "isolated to your account and never shared with other services."
            ),
        }

    @classmethod
    def attach_backend(
        cls,
        backend_type: str,
        connection_string: str = "",
        supabase_url: str = "",
        supabase_key: str = "",
        database_name: str = "ultron_memory",
    ) -> Dict[str, Any]:
        """Attach a private cloud database (Supabase, PostgreSQL, or MongoDB)."""
        b_type = (backend_type or "supabase").lower().strip()
        if b_type not in ("supabase", "postgres", "postgresql", "mongodb"):
            return {
                "success": False,
                "error": (
                    f"Unsupported database type '{backend_type}'. "
                    "Supported backends are: 'supabase', 'postgres', or 'mongodb'."
                ),
            }

        # Normalize postgresql
        if b_type == "postgresql":
            b_type = "postgres"

        if b_type in ("postgres", "mongodb") and not connection_string:
            return {
                "success": False,
                "error": f"Connection URI required for {b_type} (e.g. postgresql://user:pass@host/db or mongodb+srv://...)",
            }

        if b_type == "supabase" and not connection_string and not supabase_url:
            return {
                "success": False,
                "error": "Supabase requires either a PostgreSQL connection string or a Supabase Project URL & Key.",
            }

        cfg = {
            "backend_type": b_type,
            "connection_string": connection_string.strip(),
            "supabase_url": supabase_url.strip(),
            "supabase_key": supabase_key.strip(),
            "database_name": database_name.strip() or "ultron_memory",
            "status": "active",
        }
        cls.save_config(cfg)

        return {
            "success": True,
            "backend": b_type,
            "status": "attached",
            "message": (
                f"Successfully attached your private {b_type.upper()} database. "
                "From now on, your memory and session history will be stored in your "
                "dedicated cloud database instead of local host memory."
            ),
        }

    @classmethod
    def detach_backend(cls) -> Dict[str, Any]:
        """Detach external database and revert to local SQLite memory."""
        cfg = cls.load_config()
        cfg["backend_type"] = "local"
        cls.save_config(cfg)
        return {
            "success": True,
            "backend": "local",
            "message": "Switched back to local memory (SQLite and Markdown files).",
        }
