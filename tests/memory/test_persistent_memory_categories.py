"""Tests for Persistent Memory with categories, project scoping, lifecycle updates, and sensitive data scrubbing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from openjarvis.memory.store import (
    Fact,
    LocalFactStore,
    MEMORY_CATEGORIES,
    TRUST_AUTO,
    TRUST_TRUSTED,
    TRUST_UNTRUSTED,
    scrub_sensitive_data,
)


@pytest.fixture
def temp_store(tmp_path: Path) -> LocalFactStore:
    jsonl_path = tmp_path / "memory_facts.jsonl"
    return LocalFactStore(path=jsonl_path)


def test_memory_categories_defined():
    expected = {
        "general",
        "user_preferences",
        "architecture_decisions",
        "project_context",
        "successful_workflows",
        "recurring_failure_lessons",
    }
    assert expected.issubset(MEMORY_CATEGORIES)


def test_scrub_sensitive_data():
    raw = (
        "User API key is sk-1234567890123456789012345 and GitHub token is ghp_abcdefghijklmnopqrstuvwxyz1234567890. "
        "Also DB password: postgres://admin:SuperSecretPass123!@localhost:5432/mydb with authorization Bearer my_secret_token_12345678. "
        "My safety code is 849201."
    )
    scrubbed = scrub_sensitive_data(raw)
    assert "sk-1234567890123456789012345" not in scrubbed
    assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in scrubbed
    assert "SuperSecretPass123!" not in scrubbed
    assert "my_secret_token_12345678" not in scrubbed
    assert "849201" not in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed
    assert "[REDACTED_GITHUB_TOKEN]" in scrubbed
    assert "password=[REDACTED]" in scrubbed
    assert "[REDACTED_SAFETY_CODE]" in scrubbed


def test_add_and_query_categorized_memories(temp_store: LocalFactStore):
    # Add memories across various categories and projects
    temp_store.add(
        "User prefers TypeScript over Python for frontend",
        category="user_preferences",
        project="web-portal",
        verified=True,
    )
    temp_store.add(
        "Use SQLite WAL mode for concurrency",
        category="architecture_decisions",
        project="web-portal",
        verified=True,
    )
    temp_store.add(
        "Avoid using deprecated API endpoint /v1/status",
        category="recurring_failure_lessons",
        project="web-portal",
        verified=True,
    )
    temp_store.add(
        "Backend uses Go 1.22",
        category="architecture_decisions",
        project="backend-service",
        verified=True,
    )

    # Query by project and category
    pref = temp_store.query(category="user_preferences", project="web-portal")
    assert len(pref) == 1
    assert "TypeScript" in pref[0].text
    assert pref[0].verified is True

    arch_web = temp_store.query(category="architecture_decisions", project="web-portal")
    assert len(arch_web) == 1
    assert "SQLite" in arch_web[0].text

    arch_backend = temp_store.query(category="architecture_decisions", project="backend-service")
    assert len(arch_backend) == 1
    assert "Go 1.22" in arch_backend[0].text

    # Cross-project query
    all_arch = temp_store.query(category="architecture_decisions")
    assert len(all_arch) == 2


def test_persistence_across_restarts(tmp_path: Path):
    jsonl_path = tmp_path / "memory_facts.jsonl"
    store1 = LocalFactStore(path=jsonl_path)
    store1.add(
        "Project root is /src/app",
        category="project_context",
        project="my-app",
        verified=True,
        memory_id="mem_root_dir",
    )

    # Simulate restart by instantiating new store on same file
    store2 = LocalFactStore(path=jsonl_path)
    fact = store2.get("mem_root_dir")
    assert fact is not None
    assert fact.text == "Project root is /src/app"
    assert fact.category == "project_context"
    assert fact.project == "my-app"
    assert fact.verified is True


def test_update_and_delete_outdated_memory(temp_store: LocalFactStore):
    temp_store.add(
        "Use Python 3.10 for testing",
        category="architecture_decisions",
        project="test-proj",
        memory_id="mem_python_version",
    )

    # Verify initial fact
    fact = temp_store.get("mem_python_version")
    assert fact is not None
    assert "Python 3.10" in fact.text

    # Update outdated memory to 3.12
    updated = temp_store.update(
        "mem_python_version",
        text="Use Python 3.12 for testing",
        verified=True,
    )
    assert updated is True

    fact_updated = temp_store.get("mem_python_version")
    assert fact_updated is not None
    assert "Python 3.12" in fact_updated.text
    assert fact_updated.verified is True

    # Delete memory
    deleted = temp_store.delete("mem_python_version")
    assert deleted is True
    assert temp_store.get("mem_python_version") is None
    assert len(temp_store.query(project="test-proj")) == 0


def test_scrub_sensitive_data_on_store_add(temp_store: LocalFactStore):
    temp_store.add(
        "Saved master token: ghp_999999999999999999999999999999999999",
        category="project_context",
        project="secure-proj",
        memory_id="mem_token",
    )
    fact = temp_store.get("mem_token")
    assert fact is not None
    assert "ghp_" not in fact.text
    assert "[REDACTED_GITHUB_TOKEN]" in fact.text
