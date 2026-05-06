from __future__ import annotations

from aps_sdk.types.task import TaskEnvelope, TaskState


class InvalidTransitionError(Exception):
    def __init__(self, from_state: TaskState, to_state: TaskState):
        super().__init__(f"Invalid transition: {from_state.value} -> {to_state.value}")
        self.from_state = from_state
        self.to_state = to_state


TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.DELEGATED, TaskState.CANCELLED},
    TaskState.DELEGATED: {TaskState.ACCEPTED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.ACCEPTED: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


class TaskLifecycle:
    def __init__(self, task: TaskEnvelope):
        self.task = task

    def transition(self, to_state: TaskState) -> None:
        valid = TRANSITIONS.get(self.task.state, set())
        if to_state not in valid:
            raise InvalidTransitionError(self.task.state, to_state)
        self.task.state = to_state

    @property
    def is_terminal(self) -> bool:
        return self.task.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
