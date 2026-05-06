import pytest
import httpx
from aps_sdk import Agent, Intent, TaskEnvelope
from aps_sdk.server import create_agent_app


@pytest.fixture
def echo_agent():
    agent = Agent(name="echo")

    @agent.capability("echo")
    async def echo_handler(task: TaskEnvelope) -> dict:
        return {"echoed": task.intent.params.get("message", "")}

    return agent


async def test_agent_server_handles_task(echo_agent):
    """POST /aps/tasks dispatches to registered capability and returns result."""
    app = create_agent_app(echo_agent)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        task = TaskEnvelope(intent=Intent(type="echo", params={"message": "hello"}))
        resp = await client.post("/aps/tasks", content=task.model_dump_json())
    assert resp.status_code == 200
    assert resp.json()["result"]["echoed"] == "hello"


async def test_agent_server_rejects_unknown_capability(echo_agent):
    """POST /aps/tasks returns 400 for unknown capability."""
    app = create_agent_app(echo_agent)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        task = TaskEnvelope(intent=Intent(type="unknown", params={}))
        resp = await client.post("/aps/tasks", content=task.model_dump_json())
    assert resp.status_code == 400
    assert "No handler" in resp.json()["detail"]


async def test_agent_server_health(echo_agent):
    """GET /health returns ok with agent name and DID."""
    app = create_agent_app(echo_agent)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["agent"] == "echo"
    assert "did:aps:" in data["did"]
