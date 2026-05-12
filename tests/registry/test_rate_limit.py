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


async def test_rate_limit_publish(client):
    """POST /v1/agents is limited to 10/minute; 11th call returns 429."""
    for i in range(10):
        _, pub = generate_keypair()
        agent_did = did_from_public_key(pub)
        resp = await client.post(
            "/v1/agents",
            json={
                "did": agent_did,
                "name": f"Agent {i}",
                "capabilities": ["test"],
                "endpoint": f"http://test:{9000 + i}",
            },
        )
        assert resp.status_code == 201, f"Request {i} failed: {resp.text}"

    _, pub = generate_keypair()
    over_did = did_from_public_key(pub)
    resp = await client.post(
        "/v1/agents",
        json={
            "did": over_did,
            "name": "Over Limit",
            "capabilities": ["test"],
            "endpoint": "http://test:9999",
        },
    )
    assert resp.status_code == 429


async def test_rate_limit_search(client):
    """GET /v1/agents/query is limited to 60/minute; 61st call returns 429."""
    for i in range(60):
        resp = await client.get("/v1/agents/query", params={"capability": "test"})
        assert resp.status_code == 200, f"Request {i} failed: {resp.text}"

    resp = await client.get("/v1/agents/query", params={"capability": "test"})
    assert resp.status_code == 429


async def test_rate_limit_get_agent(client):
    """GET /v1/agents/{did} is limited to 60/minute; 61st call returns 429."""
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    resp = await client.post(
        "/v1/agents",
        json={
            "did": agent_did,
            "name": "Get Agent",
            "capabilities": ["test"],
            "endpoint": "http://test:8000",
        },
    )
    assert resp.status_code == 201

    for i in range(60):
        resp = await client.get(f"/v1/agents/{agent_did}")
        assert resp.status_code == 200, f"Request {i} failed: {resp.text}"

    resp = await client.get(f"/v1/agents/{agent_did}")
    assert resp.status_code == 429
