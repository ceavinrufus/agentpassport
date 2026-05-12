import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from aps_sdk.identity.did import generate_keypair, did_from_public_key
from aps_sdk.registry_client import RegistryClient
from aps_sdk.types import AgentCard, CostInfo


async def test_discover_agents_by_capability():
    """RegistryClient.discover() queries registry and returns AgentCards."""
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "did": agent_did,
            "name": "test-agent",
            "capabilities": ["log_search"],
            "endpoint": "http://localhost:8101",
            "cost": {"credits_per_task": 0.1},
        }
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        client = RegistryClient(registry_url="http://localhost:9000")
        agents = await client.discover(capability="log_search")

    assert len(agents) == 1
    assert agents[0].did == agent_did
    assert "log_search" in agents[0].capabilities


async def test_discover_with_cost_filter():
    """RegistryClient.discover() passes cost filter as query param."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response
    ) as mock_get:
        client = RegistryClient(registry_url="http://localhost:9000")
        await client.discover(capability="notify", max_cost=0.5)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["max_cost"] == 0.5


async def test_publish_agent_card():
    """RegistryClient.publish() posts card and returns response."""
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    card = AgentCard(
        did=agent_did,
        name="my-agent",
        capabilities=["search"],
        endpoint="http://localhost:8100",
        cost=CostInfo(credits_per_task=0.1),
    )
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 201
    mock_response.json.return_value = {"status": "registered", "did": card.did}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        client = RegistryClient(registry_url="http://localhost:9000")
        result = await client.publish(card)

    assert result["status"] == "registered"
