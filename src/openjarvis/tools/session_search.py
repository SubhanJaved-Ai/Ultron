"""SessionSearchTool — long-term conversation recall across past sessions.

Directly inspired by Hermes Agent's session_search_tool: provides four inferred modes:
1. DISCOVERY (query provided): SQLite FTS5 BM25 search across past turns.
2. SCROLL (session_id + around_message_id): message window around an anchor.
3. READ (session_id provided alone): bounded transcript of a past session.
4. BROWSE (no args): overview of recent sessions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from openjarvis.core.config import DEFAULT_CONFIG_DIR
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.sessions.session import SessionStore
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("session_search")
class SessionSearchTool(BaseTool):
    """Search and recall past conversation history across sessions."""

    tool_id = "session_search"

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self._db_path = Path(db_path) if db_path else DEFAULT_CONFIG_DIR / "sessions.db"
        self._store: Optional[SessionStore] = None

    def _get_store(self) -> SessionStore:
        if self._store is None:
            self._store = SessionStore(db_path=self._db_path)
        return self._store

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="session_search",
            description=(
                "Recall past conversations across sessions using SQLite full-text search. "
                "Inferred modes: "
                "1) DISCOVERY (query provided): search past messages across sessions. "
                "2) SCROLL (session_id + around_message_id): view conversation window around an anchor message. "
                "3) READ (session_id alone): read full/bounded transcript of a session. "
                "4) BROWSE (no arguments): list recent conversation sessions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or search term for discovery mode.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to inspect, scroll, or read.",
                    },
                    "around_message_id": {
                        "type": "integer",
                        "description": "Message ID to scroll around (returns a context window).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 20).",
                    },
                    "window": {
                        "type": "integer",
                        "description": "Context window size for scroll mode (default: 5).",
                    },
                },
            },
            category="memory",
        )

    def execute(self, **params: Any) -> ToolResult:
        store = self._get_store()
        query = (params.get("query") or "").strip()
        session_id = (params.get("session_id") or "").strip()
        around_message_id = params.get("around_message_id")
        limit = int(params.get("limit") or 20)
        window = int(params.get("window") or 5)

        # Mode 1: DISCOVERY
        if query:
            results = store.search_messages(
                query, limit=limit, session_id=session_id or None
            )
            if not results:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=True,
                    content=f"No matching conversation turns found for query: '{query}'",
                )
            lines = [f"Found {len(results)} matches for '{query}':"]
            for r in results:
                snippet = r["snippet"].replace("<b>", "[").replace("</b>", "]")
                lines.append(
                    f"- [Session {r['session_id']} | Msg #{r['message_id']} | {r['role']}]: {snippet}"
                )
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="\n".join(lines),
            )

        # Mode 2: SCROLL
        if session_id and around_message_id is not None:
            context_msgs = store.get_message_context(
                session_id, int(around_message_id), window=window
            )
            if not context_msgs:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"No context found around message #{around_message_id} in session {session_id}.",
                )
            lines = [
                f"Conversation window around message #{around_message_id} in session {session_id}:"
            ]
            for m in context_msgs:
                marker = (
                    " >>> " if m["message_id"] == int(around_message_id) else "     "
                )
                lines.append(
                    f"{marker}[Msg #{m['message_id']} | {m['role']}]: {m['content']}"
                )
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="\n".join(lines),
            )

        # Mode 3: READ
        if session_id:
            transcript = store.get_session_transcript(session_id, limit=limit)
            if not transcript:
                return ToolResult(
                    tool_name=self.spec.name,
                    success=False,
                    content=f"No messages found for session: {session_id}",
                )
            lines = [f"Transcript for session {session_id}:"]
            for m in transcript:
                lines.append(f"[{m['role'].upper()}]: {m['content']}")
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="\n".join(lines),
            )

        # Mode 4: BROWSE
        sessions = store.list_sessions(active_only=False, limit=limit)
        if not sessions:
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="No past sessions found in database.",
            )
        lines = [f"Recent sessions ({len(sessions)}):"]
        for s in sessions:
            lines.append(
                f"- Session {s.session_id} | User: {s.identity.user_id if s.identity else 'anonymous'} | Messages: {len(s.messages)}"
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content="\n".join(lines),
        )
