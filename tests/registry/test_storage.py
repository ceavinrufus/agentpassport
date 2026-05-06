import pytest
from aps_registry.storage.sqlite import SqliteStorage
from aps_sdk.types import AgentCard, CostInfo


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    s = SqliteStorage(str(db_path))
    s.initialize()
    return s


def test_register_and_get(storage):
    card = AgentCard(
        did="did:aps:test123",
        name="Test Agent",
        capabilities=["search", "summarize"],
        endpoint="http://localhost:9000",
        cost=CostInfo(per_task=0.01),
        latency_p99_ms=500,
    )
    storage.register(card)
    result = storage.get("did:aps:test123")
    assert result is not None
    assert result.name == "Test Agent"
    assert result.capabilities == ["search", "summarize"]


def test_get_nonexistent(storage):
    result = storage.get("did:aps:nope")
    assert result is None


def test_delete(storage):
    card = AgentCard(
        did="did:aps:del",
        name="To Delete",
        capabilities=["x"],
        endpoint="http://localhost:9001",
    )
    storage.register(card)
    storage.delete("did:aps:del")
    assert storage.get("did:aps:del") is None
