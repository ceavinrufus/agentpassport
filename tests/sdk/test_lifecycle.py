import pytest
from aps_sdk.task.lifecycle import InvalidTransitionError, TaskLifecycle
from aps_sdk.types import Intent, TaskEnvelope, TaskState


def test_valid_transitions():
    task = TaskEnvelope(intent=Intent(type="search", params={}))
    lc = TaskLifecycle(task)

    lc.transition(TaskState.DELEGATED)
    assert lc.task.state == TaskState.DELEGATED

    lc.transition(TaskState.ACCEPTED)
    assert lc.task.state == TaskState.ACCEPTED

    lc.transition(TaskState.RUNNING)
    lc.transition(TaskState.COMPLETED)
    assert lc.task.state == TaskState.COMPLETED


def test_invalid_transition_raises():
    task = TaskEnvelope(intent=Intent(type="search", params={}))
    lc = TaskLifecycle(task)

    with pytest.raises(InvalidTransitionError):
        lc.transition(TaskState.COMPLETED)  # Can't go from CREATED -> COMPLETED
