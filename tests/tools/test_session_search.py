"""Tests for SessionSearchTool: discovery, scroll, read, and browse modes."""

from pathlib import Path

from openjarvis.sessions.session import SessionStore
from openjarvis.tools.session_search import SessionSearchTool


def test_session_search_discovery_and_read(tmp_path: Path):
    db_path = tmp_path / "sessions.db"
    store = SessionStore(db_path=db_path)
    session = store.get_or_create("dev_alice")
    sid = session.session_id

    store.save_message(sid, "user", "Let's debug the subagent timeout problem.")
    store.save_message(
        sid, "assistant", "Check if the worker heartbeat interval is set to 30s."
    )
    store.close()

    tool = SessionSearchTool(db_path=db_path)

    # 1. Discovery mode
    res_disc = tool.execute(query="heartbeat")
    assert res_disc.success is True
    assert "Found 1 matches" in res_disc.content
    assert "heartbeat" in res_disc.content

    # 2. Read mode
    res_read = tool.execute(session_id=sid)
    assert res_read.success is True
    assert f"Transcript for session {sid}" in res_read.content
    assert "timeout problem" in res_read.content

    # 3. Scroll mode
    res_scroll = tool.execute(session_id=sid, around_message_id=1, window=1)
    assert res_scroll.success is True
    assert "Conversation window" in res_scroll.content

    # 4. Browse mode
    res_browse = tool.execute()
    assert res_browse.success is True
    assert f"Session {sid}" in res_browse.content
