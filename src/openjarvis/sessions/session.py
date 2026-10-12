"""Session management — cross-channel persistent sessions.

Supports consolidation and decay.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SessionIdentity:
    """Canonical user identity across channels."""

    user_id: str
    display_name: str = ""
    # channel_type -> channel_user_id
    channel_ids: Dict[str, str] = field(
        default_factory=dict,
    )


@dataclass(slots=True)
class SessionMessage:
    """A single message within a session."""

    role: str  # "user" | "assistant" | "system"
    content: str
    channel: str = ""
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """A conversation session with cross-channel message history."""

    session_id: str = ""
    identity: Optional[SessionIdentity] = None
    messages: List[SessionMessage] = field(default_factory=list)
    created_at: float = 0.0
    last_activity: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, *, channel: str = "") -> None:
        self.messages.append(
            SessionMessage(
                role=role,
                content=content,
                channel=channel,
                timestamp=time.time(),
            )
        )
        self.last_activity = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.identity.user_id if self.identity else "",
            "display_name": self.identity.display_name if self.identity else "",
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "metadata": self.metadata,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "channel": m.channel,
                    "timestamp": m.timestamp,
                }
                for m in self.messages
            ],
            "message_count": len(self.messages),
        }


class SessionStore:
    """SQLite-backed session persistence with consolidation and decay."""

    def __init__(
        self,
        db_path: Union[str, Path, None] = None,
        *,
        max_age_hours: float = 24.0,
        consolidation_threshold: int = 100,
    ) -> None:
        if db_path is None:
            from openjarvis.core.paths import get_config_dir

            db_path = get_config_dir() / "sessions.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._max_age_hours = max_age_hours
        self._consolidation_threshold = consolidation_threshold
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id    TEXT PRIMARY KEY,
                user_id       TEXT,
                display_name  TEXT DEFAULT '',
                channel_ids   TEXT DEFAULT '{}',
                created_at    REAL,
                last_activity REAL,
                metadata      TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS session_messages (
                id         INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                channel    TEXT DEFAULT '',
                timestamp  REAL,
                metadata   TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON session_messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_user
                ON sessions(user_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts USING fts5(
                content,
                session_id UNINDEXED,
                role UNINDEXED,
                channel UNINDEXED,
                tokenize='unicode61'
            );
            CREATE TRIGGER IF NOT EXISTS trg_session_messages_ai AFTER INSERT ON session_messages BEGIN
                INSERT INTO session_messages_fts(rowid, content, session_id, role, channel)
                VALUES (new.id, new.content, new.session_id, new.role, new.channel);
            END;
            CREATE TRIGGER IF NOT EXISTS trg_session_messages_ad AFTER DELETE ON session_messages BEGIN
                DELETE FROM session_messages_fts WHERE rowid = old.id;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_session_messages_au AFTER UPDATE ON session_messages BEGIN
                DELETE FROM session_messages_fts WHERE rowid = old.id;
                INSERT INTO session_messages_fts(rowid, content, session_id, role, channel)
                VALUES (new.id, new.content, new.session_id, new.role, new.channel);
            END;
        """)
        # Backfill any pre-existing messages not yet in FTS5
        try:
            self._conn.execute("""
                INSERT INTO session_messages_fts(rowid, content, session_id, role, channel)
                SELECT id, content, session_id, role, channel FROM session_messages
                WHERE id NOT IN (SELECT rowid FROM session_messages_fts);
            """)
        except Exception:
            pass
        self._conn.commit()

    def get_or_create(
        self,
        user_id: str,
        *,
        channel: str = "",
        channel_user_id: str = "",
        display_name: str = "",
    ) -> Session:
        """Get existing session for user or create a new one."""
        row = self._conn.execute(
            "SELECT session_id, user_id, display_name,"
            " channel_ids, created_at, last_activity,"
            " metadata "
            "FROM sessions WHERE user_id = ?"
            " ORDER BY last_activity DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        if row:
            session_id = row[0]
            # Check age
            age_hours = (time.time() - (row[5] or 0)) / 3600
            if age_hours > self._max_age_hours:
                # Session expired, create new
                return self._create_session(
                    user_id,
                    channel,
                    channel_user_id,
                    display_name,
                )

            channel_ids = json.loads(row[3]) if row[3] else {}
            if channel and channel_user_id:
                channel_ids[channel] = channel_user_id
                self._conn.execute(
                    "UPDATE sessions SET channel_ids = ?,"
                    " last_activity = ?"
                    " WHERE session_id = ?",
                    (json.dumps(channel_ids), time.time(), session_id),
                )
                self._conn.commit()

            # Load messages
            messages = self._load_messages(session_id)

            return Session(
                session_id=session_id,
                identity=SessionIdentity(
                    user_id=row[1],
                    display_name=row[2] or display_name,
                    channel_ids=channel_ids,
                ),
                messages=messages,
                created_at=row[4] or 0.0,
                last_activity=row[5] or 0.0,
                metadata=json.loads(row[6]) if row[6] else {},
            )

        return self._create_session(user_id, channel, channel_user_id, display_name)

    def _create_session(
        self,
        user_id: str,
        channel: str,
        channel_user_id: str,
        display_name: str,
    ) -> Session:
        session_id = uuid.uuid4().hex[:16]
        now = time.time()
        channel_ids = {channel: channel_user_id} if channel and channel_user_id else {}
        self._conn.execute(
            "INSERT INTO sessions (session_id, user_id,"
            " display_name, channel_ids,"
            " created_at, last_activity) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, display_name, json.dumps(channel_ids), now, now),
        )
        self._conn.commit()
        return Session(
            session_id=session_id,
            identity=SessionIdentity(
                user_id=user_id,
                display_name=display_name,
                channel_ids=channel_ids,
            ),
            created_at=now,
            last_activity=now,
        )

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        channel: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a message to a session."""
        self._conn.execute(
            "INSERT INTO session_messages"
            " (session_id, role, content,"
            " channel, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                channel,
                time.time(),
                json.dumps(metadata or {}),
            ),
        )
        self._conn.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (time.time(), session_id),
        )
        self._conn.commit()

        # Check if consolidation is needed
        count = self._conn.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        if count > self._consolidation_threshold:
            self.consolidate(session_id)

    def consolidate(self, session_id: str) -> None:
        """Consolidate old messages: summarize oldest half, keep recent half."""
        messages = self._load_messages(session_id)
        if len(messages) <= self._consolidation_threshold // 2:
            return

        split = len(messages) // 2
        old_messages = messages[:split]

        # Create summary of old messages
        summary_parts = []
        for msg in old_messages[:10]:  # summarize first 10 of old batch
            summary_parts.append(f"[{msg.role}] {msg.content[:100]}")
        summary = "Session history summary:\n" + "\n".join(summary_parts)

        # Delete old messages
        oldest_ts = old_messages[-1].timestamp if old_messages else 0
        self._conn.execute(
            "DELETE FROM session_messages WHERE session_id = ? AND timestamp <= ?",
            (session_id, oldest_ts),
        )
        # Insert summary as system message
        self._conn.execute(
            "INSERT INTO session_messages"
            " (session_id, role, content,"
            " channel, timestamp) "
            "VALUES (?, 'system', ?, '', ?)",
            (session_id, summary, time.time()),
        )
        self._conn.commit()

    def decay(self, max_age_hours: Optional[float] = None) -> int:
        """Remove sessions older than max_age_hours. Returns count removed."""
        age = max_age_hours or self._max_age_hours
        cutoff = time.time() - (age * 3600)
        cur = self._conn.execute(
            "SELECT session_id FROM sessions WHERE last_activity < ?",
            (cutoff,),
        )
        session_ids = [row[0] for row in cur.fetchall()]
        for sid in session_ids:
            self._conn.execute(
                "DELETE FROM session_messages WHERE session_id = ?",
                (sid,),
            )
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (sid,),
            )
        self._conn.commit()
        return len(session_ids)

    def link_channel(self, session_id: str, channel: str, channel_user_id: str) -> None:
        """Link a channel identity to an existing session."""
        row = self._conn.execute(
            "SELECT channel_ids FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row:
            channel_ids = json.loads(row[0]) if row[0] else {}
            channel_ids[channel] = channel_user_id
            self._conn.execute(
                "UPDATE sessions SET channel_ids = ? WHERE session_id = ?",
                (json.dumps(channel_ids), session_id),
            )
            self._conn.commit()

    def list_sessions(
        self,
        *,
        active_only: bool = True,
        limit: int = 50,
        user_id: Optional[str] = None,
    ) -> List[Session]:
        """List sessions, optionally filtering to active only and/or specific user."""
        sql = (
            "SELECT session_id, user_id, display_name,"
            " channel_ids, created_at, last_activity,"
            " metadata FROM sessions"
        )
        where_clauses = []
        params: list = []
        if active_only:
            cutoff = time.time() - (self._max_age_hours * 3600)
            where_clauses.append("last_activity >= ?")
            params.append(cutoff)
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY last_activity DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        sessions = []
        for row in rows:
            sessions.append(
                Session(
                    session_id=row[0],
                    identity=SessionIdentity(
                        user_id=row[1],
                        display_name=row[2] or "",
                        channel_ids=json.loads(row[3]) if row[3] else {},
                    ),
                    created_at=row[4] or 0.0,
                    last_activity=row[5] or 0.0,
                    metadata=json.loads(row[6]) if row[6] else {},
                )
            )
        return sessions

    def recent(self, limit: int = 20, user_id: Optional[str] = None) -> List[Session]:
        """Get recent sessions for user."""
        return self.list_sessions(active_only=False, limit=limit, user_id=user_id)

    def get_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Session]:
        """Get a specific session with optional user ownership check."""
        row = self._conn.execute(
            "SELECT session_id, user_id, display_name,"
            " channel_ids, created_at, last_activity, metadata "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None

        # Enforce tenant isolation if user_id is provided
        if user_id and row[1] != user_id:
            return None

        messages = self._load_messages(session_id)
        return Session(
            session_id=row[0],
            identity=SessionIdentity(
                user_id=row[1],
                display_name=row[2] or "",
                channel_ids=json.loads(row[3]) if row[3] else {},
            ),
            messages=messages,
            created_at=row[4] or 0.0,
            last_activity=row[5] or 0.0,
            metadata=json.loads(row[6]) if row[6] else {},
        )

    def _load_messages(self, session_id: str) -> List[SessionMessage]:
        rows = self._conn.execute(
            "SELECT role, content, channel, timestamp, metadata "
            "FROM session_messages WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [
            SessionMessage(
                role=row[0],
                content=row[1],
                channel=row[2] or "",
                timestamp=row[3] or 0.0,
                metadata=json.loads(row[4]) if row[4] else {},
            )
            for row in rows
        ]

    def search_messages(
        self,
        query: str,
        limit: int = 20,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform full-text search across session messages using SQLite FTS5."""
        if not query.strip():
            return []

        # Sanitize FTS5 query: replace punctuation with space so terms match token boundaries
        clean_query = re.sub(r"[^\w\s]", " ", query)
        safe_terms = [t for t in clean_query.split() if t]
        if not safe_terms:
            return []
        fts_query = " ".join(f'"{t}"' for t in safe_terms)

        try:
            if session_id:
                cur = self._conn.execute(
                    """
                    SELECT m.id, m.session_id, m.role, m.content, m.channel, m.timestamp,
                           snippet(session_messages_fts, 0, '<b>', '</b>', '...', 20),
                           rank
                    FROM session_messages_fts f
                    JOIN session_messages m ON f.rowid = m.id
                    WHERE session_messages_fts MATCH ? AND m.session_id = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, session_id, limit),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT m.id, m.session_id, m.role, m.content, m.channel, m.timestamp,
                           snippet(session_messages_fts, 0, '<b>', '</b>', '...', 20),
                           rank
                    FROM session_messages_fts f
                    JOIN session_messages m ON f.rowid = m.id
                    WHERE session_messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                )
            rows = cur.fetchall()
            return [
                {
                    "message_id": row[0],
                    "session_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "channel": row[4],
                    "timestamp": row[5],
                    "snippet": row[6],
                    "rank": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("FTS search error: %s", e)
            return []

    def get_message_context(
        self,
        session_id: str,
        around_message_id: int,
        window: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve a window of messages around a target message id."""
        min_id = max(1, around_message_id - window)
        max_id = around_message_id + window
        cur = self._conn.execute(
            """
            SELECT id, session_id, role, content, channel, timestamp
            FROM session_messages
            WHERE session_id = ? AND id BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (session_id, min_id, max_id),
        )
        return [
            {
                "message_id": row[0],
                "session_id": row[1],
                "role": row[2],
                "content": row[3],
                "channel": row[4],
                "timestamp": row[5],
            }
            for row in cur.fetchall()
        ]

    def get_session_transcript(
        self,
        session_id: str,
        max_chars_per_msg: int = 2000,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve bounded messages for a complete session transcript."""
        cur = self._conn.execute(
            """
            SELECT id, role, content, channel, timestamp
            FROM session_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (session_id, limit),
        )
        results = []
        for row in cur.fetchall():
            content = row[2]
            if len(content) > max_chars_per_msg:
                content = content[:max_chars_per_msg] + "... [truncated]"
            results.append(
                {
                    "message_id": row[0],
                    "role": row[1],
                    "content": content,
                    "channel": row[3],
                    "timestamp": row[4],
                }
            )
        return results

    def close(self) -> None:
        self._conn.close()


__all__ = ["Session", "SessionIdentity", "SessionMessage", "SessionStore"]
