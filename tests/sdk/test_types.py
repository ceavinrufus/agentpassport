import uuid
from aps_sdk.types.task import TaskEnvelope, Intent, Constraints, FailurePolicy, TaskState
from aps_sdk.types.identity import AuthEntry
from aps_sdk.types.agent_card import AgentCard, CostInfo
from aps_sdk.types.events import ObservabilityEvent


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


def test_auth_entry_round_trip():
    entry = AuthEntry(
        issuer="did:aps:abc",
        subject="did:aps:xyz",
        scope=["search"],
        issued_at="2026-05-07T00:00:00Z",
        expires_at="2026-05-07T01:00:00Z",
        sig="deadbeef",
    )
    data = entry.model_dump()
    restored = AuthEntry.model_validate(data)
    assert restored.issuer == entry.issuer
    assert restored.sig == entry.sig


def test_agent_card_round_trip():
    card = AgentCard(
        did="did:aps:searcher",
        name="Searcher",
        capabilities=["search"],
        endpoint="http://localhost:9000",
        cost=CostInfo(per_task=0.01),
        latency_p99_ms=300,
    )
    data = card.model_dump()
    restored = AgentCard.model_validate(data)
    assert restored.did == card.did
    assert restored.capabilities == ["search"]
    assert restored.cost.per_task == 0.01


def test_observability_event_round_trip():
    evt = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_created",
        agent="did:aps:planner",
        cost_used=0.0,
        budget_remaining=10.0,
    )
    data = evt.model_dump()
    restored = ObservabilityEvent.model_validate(data)
    assert restored.trace_id == evt.trace_id
    assert restored.event == "task_created"
