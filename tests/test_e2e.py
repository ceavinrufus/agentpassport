"""End-to-end test: agent creates task, delegates, budget enforced, events emitted."""

import pytest
from aps_sdk import (
    Agent,
    BudgetTracker,
    Constraints,
    EventEmitter,
    Intent,
    MemorySink,
    TaskEnvelope,
    create_subtask,
)


async def test_full_delegation_flow():
    sink = MemorySink()
    emitter = EventEmitter(sinks=[sink])

    _planner = Agent(name="planner", emitter=emitter)
    searcher = Agent(name="searcher", emitter=emitter)

    @searcher.capability("search")
    async def handle_search(task: TaskEnvelope) -> dict:
        return {"results": ["result1", "result2"]}

    root_task = TaskEnvelope(
        intent=Intent(type="plan", params={"goal": "find info"}),
        constraints=Constraints(budget_credits=10),
    )

    budget = BudgetTracker(total_credits=root_task.constraints.budget_credits)
    subtask = create_subtask(
        parent=root_task,
        intent=Intent(type="search", params={"q": "hello"}),
        budget_credits=5,
        budget_tracker=budget,
    )

    assert subtask.parent_id == root_task.id
    assert subtask.trace_id == root_task.trace_id
    assert budget.remaining == 5.0

    result = await searcher.handle(subtask)
    assert result == {"results": ["result1", "result2"]}

    assert len(sink.events) >= 2
    event_types = [e.event for e in sink.events]
    assert "task_accepted" in event_types
    assert "task_completed" in event_types


async def test_budget_prevents_over_delegation():
    budget = BudgetTracker(total_credits=5)
    task = TaskEnvelope(
        intent=Intent(type="plan", params={}),
        constraints=Constraints(budget_credits=5),
    )

    from aps_sdk.task.budget import BudgetExceededError

    _subtask1 = create_subtask(task, Intent(type="a", params={}), 3, budget)
    assert budget.remaining == 2.0

    with pytest.raises(BudgetExceededError):
        create_subtask(task, Intent(type="b", params={}), 3, budget)
