"""Tests for WebhookTriggerRegistry: inbound automation triggers."""

from pathlib import Path

from openjarvis.server.webhook_trigger import WebhookTriggerRegistry


def test_webhook_trigger_registry_crud(tmp_path: Path):
    db_path = tmp_path / "triggers.db"
    reg = WebhookTriggerRegistry(db_path=db_path)

    # 1. Register trigger
    t = reg.register(
        slug="github-push",
        target_type="workflow",
        target_name="ci_pipeline",
        secret_token="supersecret123",
        description="Trigger on GitHub push events",
    )
    assert t.slug == "github-push"
    assert t.target_type == "workflow"
    assert t.secret_token == "supersecret123"

    # 2. Get trigger
    fetched = reg.get("github-push")
    assert fetched is not None
    assert fetched.target_name == "ci_pipeline"

    # 3. List triggers
    all_trigs = reg.list_all()
    assert len(all_trigs) == 1
    assert all_trigs[0].slug == "github-push"

    # 4. Delete trigger
    deleted = reg.delete("github-push")
    assert deleted is True
    assert reg.get("github-push") is None

    reg.close()
