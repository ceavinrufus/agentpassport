from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.identity.signing import _decode_jwt_claims, sign_delegation
from agentpassport.types.agent_card import AgentCard, CostInfo
from agentpassport.types.events import ObservabilityEvent
from agentpassport.types.task import Constraints, Intent, TaskEnvelope, TaskState


def test_task_envelope_creation():
    task = TaskEnvelope(
        intent=Intent(type="search", params={"query": "hello"}),
        constraints=Constraints(budget_credits=10, deadline_ms=5000),
    )
    assert task.version == "1.0"
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


def test_auth_chain_jwt_round_trip():
    """auth_chain is list[str]; JWT strings survive TaskEnvelope serialisation."""
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(priv_a, did_a, did_b, ["read:db:customers"])

    task = TaskEnvelope(
        intent=Intent(type="query", params={}),
        auth_chain=[token],
    )
    data = task.model_dump()
    restored = TaskEnvelope.model_validate(data)

    assert len(restored.auth_chain) == 1
    assert restored.auth_chain[0] == token

    claims = _decode_jwt_claims(restored.auth_chain[0])
    assert claims["iss"] == did_a
    assert claims["sub"] == did_b
    assert claims["scope"] == ["read:db:customers"]
    assert "jti" in claims


def test_agent_card_round_trip():
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    card = AgentCard(
        did=agent_did,
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
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    evt = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_created",
        agent=agent_did,
        cost_used=0.0,
        budget_remaining=10.0,
    )
    data = evt.model_dump()
    restored = ObservabilityEvent.model_validate(data)
    assert restored.trace_id == evt.trace_id
    assert restored.event == "task_created"
