import pytest
from agentpassport_registry.app import create_app
from agentpassport.identity.did import generate_keypair, did_from_public_key
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=str(tmp_path / "test.db"))


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_publish_and_query(client):
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    card = {
        "did": agent_did,
        "name": "Test Pub",
        "capabilities": ["search"],
        "endpoint": "http://test:8000",
    }
    resp = await client.post("/v1/agents", json=card)
    assert resp.status_code == 201

    resp = await client.get("/v1/agents/query", params={"capability": "search"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["did"] == agent_did


async def test_get_agent(client):
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    card = {
        "did": agent_did,
        "name": "Get Me",
        "capabilities": ["write"],
        "endpoint": "http://test:8001",
    }
    await client.post("/v1/agents", json=card)

    resp = await client.get(f"/v1/agents/{agent_did}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Me"
