import pytest
from agentpassport_registry.storage.sqlite import SqliteStorage
from agentpassport.identity.did import generate_keypair, did_from_public_key
from agentpassport.types import AgentCard, CostInfo


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = SqliteStorage(str(db_path))
    s.initialize()
    return s


def test_register_and_get(storage):
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    card = AgentCard(
        did=agent_did,
        name="Test Agent",
        capabilities=["search", "summarize"],
        endpoint="http://localhost:9000",
        cost=CostInfo(per_task=0.01),
        latency_p99_ms=500,
    )
    storage.register(card)
    result = storage.get(agent_did)
    assert result is not None
    assert result.name == "Test Agent"
    assert result.capabilities == ["search", "summarize"]


def test_get_nonexistent(storage):
    _, pub = generate_keypair()
    unknown_did = did_from_public_key(pub)
    result = storage.get(unknown_did)
    assert result is None


def test_delete(storage):
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    card = AgentCard(
        did=agent_did,
        name="To Delete",
        capabilities=["x"],
        endpoint="http://localhost:9001",
    )
    storage.register(card)
    storage.delete(agent_did)
    assert storage.get(agent_did) is None
