import pytest
from aps_registry.app import create_app
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
        resp = await client.post(
            "/v1/agents",
            json={
                "did": f"did:aps:rl{i}",
                "name": f"Agent {i}",
                "capabilities": ["test"],
                "endpoint": f"http://test:{9000 + i}",
            },
        )
        assert resp.status_code == 201, f"Request {i} failed: {resp.text}"

    resp = await client.post(
        "/v1/agents",
        json={
            "did": "did:aps:rl_over",
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
