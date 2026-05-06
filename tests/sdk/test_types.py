import uuid
from aps_sdk.types.task import TaskEnvelope, Intent, Constraints, FailurePolicy, TaskState


def test_task_envelope_creation():
    task = TaskEnvelope(
        intent=Intent(type="search", params={"query": "hello"}),
        constraints=Constraints(budget_credits=10, deadline_ms=5000),
    )
    assert task.aps_version == "1.0"
    assert task.id.startswith("task_")
    assert task.state == TaskState.CREATED
    assert task.constraints.budget_credits == 10
    assert task.parent_id is None


def test_task_envelope_budget_validation():
    """Budget must be positive."""
    import pytest

    with pytest.raises(ValueError):
        TaskEnvelope(
            intent=Intent(type="search", params={}),
            constraints=Constraints(budget_credits=-1),
        )


def test_task_state_enum():
    assert TaskState.CREATED.value == "created"
    assert TaskState.COMPLETED.value == "completed"
    assert TaskState.FAILED.value == "failed"
