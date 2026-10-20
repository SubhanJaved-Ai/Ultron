"""Tests for CronjobManageTool: add, list, run, pause, resume, status, history, remove."""

from pathlib import Path

from openjarvis.scheduler.scheduler import TaskScheduler
from openjarvis.scheduler.store import SchedulerStore
from openjarvis.tools.cronjob_manage import CronjobManageTool


def test_cronjob_manage_lifecycle(tmp_path: Path):
    db_path = tmp_path / "scheduler.db"
    store = SchedulerStore(db_path)
    scheduler = TaskScheduler(store=store)
    tool = CronjobManageTool(scheduler=scheduler, store=store, db_path=db_path)

    # 1. Add cron task
    res_add = tool.execute(
        action="add",
        prompt="Daily market summary",
        schedule="0 9 * * *",
    )
    assert res_add.success is True
    assert "Scheduled task created" in res_add.content
    task_id = res_add.metadata["task_id"]

    # 2. List tasks
    res_list = tool.execute(action="list")
    assert res_list.success is True
    assert task_id in res_list.content
    assert "Daily market summary" in res_list.content

    # 3. Status
    res_stat = tool.execute(action="status", task_id=task_id)
    assert res_stat.success is True
    assert '"status": "active"' in res_stat.content

    # 4. Pause
    res_pause = tool.execute(action="pause", task_id=task_id)
    assert res_pause.success is True
    assert "Paused" in res_pause.content

    # 5. Resume
    res_resume = tool.execute(action="resume", task_id=task_id)
    assert res_resume.success is True
    assert "Resumed" in res_resume.content

    # 6. Run now
    res_run = tool.execute(action="run", task_id=task_id)
    assert "Triggered immediate execution" in res_run.content

    # 7. History
    res_hist = tool.execute(action="history", task_id=task_id)
    assert res_hist.success is True
    assert "Execution history" in res_hist.content

    # 8. Remove
    res_rm = tool.execute(action="remove", task_id=task_id)
    assert res_rm.success is True
    assert f"Removed scheduled task: {task_id}" in res_rm.content

    # Verify deleted
    res_list_after = tool.execute(action="list")
    assert task_id not in res_list_after.content
