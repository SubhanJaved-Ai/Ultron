"""Tests for SessionStore SQLite FTS5 search and triggers."""

from pathlib import Path

from openjarvis.sessions.session import SessionStore


def test_session_fts_indexing_and_search(tmp_path: Path):
    db_path = tmp_path / "sessions.db"
    store = SessionStore(db_path=db_path)

    session = store.get_or_create("user_alpha")
    sid = session.session_id

    # Add messages
    store.save_message(sid, "user", "How do I configure the Hermes gateway on my VPS?")
    store.save_message(
        sid,
        "assistant",
        "To configure the gateway, set HERMES_PORT=8000 and run hermes start.",
    )
    store.save_message(sid, "user", "Thanks, what about persistent memory?")
    store.save_message(sid, "assistant", "Memory is stored in MEMORY.md and USER.md.")

    # Search for "gateway"
    results = store.search_messages("gateway")
    assert len(results) >= 2
    assert any("HERMES_PORT" in r["content"] for r in results)

    # Search for "MEMORY.md"
    results_mem = store.search_messages("MEMORY.md")
    assert len(results_mem) >= 1
    assert "assistant" in results_mem[0]["role"]

    # Search with session_id filter
    results_scoped = store.search_messages("gateway", session_id=sid)
    assert len(results_scoped) >= 2

    store.close()


def test_session_fts_context_and_transcript(tmp_path: Path):
    db_path = tmp_path / "sessions.db"
    store = SessionStore(db_path=db_path)

    session = store.get_or_create("user_beta")
    sid = session.session_id

    for i in range(10):
        store.save_message(
            sid, "user" if i % 2 == 0 else "assistant", f"Turn number {i} text"
        )

    # Get transcript
    transcript = store.get_session_transcript(sid, limit=5)
    assert len(transcript) == 5
    assert transcript[0]["content"] == "Turn number 0 text"

    # Context window around message 5
    context = store.get_message_context(sid, around_message_id=5, window=2)
    assert len(context) >= 3

    store.close()
