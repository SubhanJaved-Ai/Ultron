"""SQLite/FTS5 memory backend — zero-dependency default."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.events import EventType, get_event_bus
from openjarvis.core.registry import MemoryRegistry
from openjarvis.tools.storage._stubs import (
    MemoryBackend,
    RetrievalResult,
)


def _check_fts5(conn: sqlite3.Connection) -> bool:
    """Return True if the SQLite build includes FTS5."""
    try:
        opts = conn.execute("PRAGMA compile_options").fetchall()
        return any("FTS5" in o[0].upper() for o in opts)
    except sqlite3.Error:
        return False


@MemoryRegistry.register("sqlite")
class SQLiteMemory(MemoryBackend):
    """Full-text search memory backend using SQLite FTS5.

    Uses the built-in ``sqlite3`` module — no extra dependencies.
    """

    backend_id: str = "sqlite"

    def __init__(self, db_path: str | Path = "") -> None:
        if not db_path:
            from openjarvis.core.config import DEFAULT_CONFIG_DIR

            db_path = str(DEFAULT_CONFIG_DIR / "memory.db")

        self._db_path = str(db_path)

        from openjarvis import _rust_bridge

        if _rust_bridge.RUST_AVAILABLE:
            from openjarvis.tools.storage._stubs import MemoryBackendUnavailable

            try:
                _rust = _rust_bridge.get_rust_module()
                self._rust_impl = _rust.SQLiteMemory(self._db_path)
                self._conn = None
            except ImportError as exc:
                raise MemoryBackendUnavailable() from exc
        else:
            self._rust_impl = None
            db_p = Path(self._db_path)
            if str(db_p) != ":memory:":
                db_p.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout = 10000")
            if str(self._db_path) != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode = WAL")
                except sqlite3.Error:
                    pass
            self._create_tables()

    def _create_tables(self) -> None:
        if self._conn is None:
            return
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id       TEXT PRIMARY KEY,
                content  TEXT NOT NULL,
                source   TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL DEFAULT (julianday('now'))
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(
                content,
                source,
                tokenize='porter unicode61'
            );
        """)

    def store(
        self,
        content: str,
        *,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist *content* and return a unique document id."""
        if self._rust_impl is not None:
            meta_json = json.dumps(metadata) if metadata else None
            doc_id = self._rust_impl.store(content, source, meta_json)
        else:
            import uuid

            doc_id = str(uuid.uuid4())
            meta_json = json.dumps(metadata or {})
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO documents (id, content, source, metadata) "
                "VALUES (?, ?, ?, ?)",
                (doc_id, content, source, meta_json),
            )
            rowid = cur.lastrowid
            cur.execute(
                "INSERT INTO documents_fts (rowid, content, source) VALUES (?, ?, ?)",
                (rowid, content, source),
            )
            self._conn.commit()

        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_STORE,
            {
                "backend": self.backend_id,
                "doc_id": doc_id,
                "source": source,
            },
        )
        return doc_id

    def replace_source(
        self,
        source: str,
        documents: List[tuple[str, Optional[Dict[str, Any]]]],
    ) -> List[str]:
        """Atomically replace all documents associated with *source*."""
        if self._rust_impl is not None:
            payload = [
                (content, json.dumps(metadata) if metadata else None)
                for content, metadata in documents
            ]
            doc_ids = self._rust_impl.replace_source(source, payload)
        else:
            import uuid

            cur = self._conn.cursor()
            cur.execute(
                "DELETE FROM documents_fts WHERE rowid IN "
                "(SELECT rowid FROM documents WHERE source = ?)",
                (source,),
            )
            cur.execute("DELETE FROM documents WHERE source = ?", (source,))
            doc_ids = []
            for content, metadata in documents:
                doc_id = str(uuid.uuid4())
                meta_json = json.dumps(metadata or {})
                cur.execute(
                    "INSERT INTO documents (id, content, source, metadata) "
                    "VALUES (?, ?, ?, ?)",
                    (doc_id, content, source, meta_json),
                )
                rowid = cur.lastrowid
                cur.execute(
                    "INSERT INTO documents_fts (rowid, content, source) "
                    "VALUES (?, ?, ?)",
                    (rowid, content, source),
                )
                doc_ids.append(doc_id)
            self._conn.commit()

        bus = get_event_bus()
        for doc_id in doc_ids:
            bus.publish(
                EventType.MEMORY_STORE,
                {
                    "backend": self.backend_id,
                    "doc_id": doc_id,
                    "source": source,
                },
            )
        return doc_ids

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """Search via FTS5 MATCH with BM25 ranking."""
        if not query.strip():
            return []

        if self._rust_impl is not None:
            from openjarvis._rust_bridge import retrieval_results_from_json

            results = retrieval_results_from_json(
                self._rust_impl.retrieve(query, top_k),
            )
        else:
            import re

            words = [w for w in re.split(r"\W+", query) if w]
            if not words:
                return []
            fts_query = " OR ".join(words)
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT d.content, d.source, d.metadata,
                       bm25(documents_fts, 1.0, 0.5) * -1 as score
                FROM documents_fts f
                JOIN documents d ON d.rowid = f.rowid
                WHERE documents_fts MATCH ?
                ORDER BY bm25(documents_fts, 1.0, 0.5)
                LIMIT ?
                """,
                (fts_query, top_k),
            )
            results = []
            for row in cur.fetchall():
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                except (json.JSONDecodeError, TypeError):
                    meta = {}
                results.append(
                    RetrievalResult(
                        content=row["content"],
                        source=row["source"] or "",
                        metadata=meta,
                        score=float(row["score"]),
                    )
                )

        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_RETRIEVE,
            {
                "backend": self.backend_id,
                "query": query,
                "num_results": len(results),
            },
        )
        return results

    def delete(self, doc_id: str) -> bool:
        """Delete a document by id."""
        if self._rust_impl is not None:
            return self._rust_impl.delete(doc_id)
        cur = self._conn.cursor()
        cur.execute(
            "DELETE FROM documents_fts WHERE rowid = "
            "(SELECT rowid FROM documents WHERE id = ?)",
            (doc_id,),
        )
        cur.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        """Remove all stored documents."""
        if self._rust_impl is not None:
            self._rust_impl.clear()
            return
        self._conn.executescript("DELETE FROM documents_fts; DELETE FROM documents;")

    def count(self) -> int:
        """Return the number of stored documents."""
        if self._rust_impl is not None:
            return self._rust_impl.count()
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None


__all__ = ["SQLiteMemory"]
