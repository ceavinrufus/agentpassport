import pytest
from unittest.mock import AsyncMock, patch
from aps_sdk import Agent, Intent, TaskEnvelope
from aps_sdk.identity import generate_keypair, did_from_public_key, sign_delegation


@pytest.fixture
def sender_agent():
    return Agent(name="sender")


@pytest.fixture
def receiver_agent():
    return Agent(name="receiver")


async def test_delegate_signs_auth_chain(sender_agent, receiver_agent):
    """When an agent delegates a task, it signs the auth chain before sending."""
    task = TaskEnvelope(intent=Intent(type="test", params={}))
    with patch.object(sender_agent._transport, "send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "ok"}
        await sender_agent.delegate(
            task=task,
            target_did=receiver_agent.did,
            endpoint="http://localhost:8101",
        )
    sent_task = mock_send.call_args[0][0]
    assert len(sent_task.auth_chain) == 1
    assert sent_task.auth_chain[0].issuer == sender_agent.did
    assert sent_task.auth_chain[0].subject == receiver_agent.did


async def test_delegate_appends_to_existing_chain(sender_agent, receiver_agent):
    """Delegation appends to existing auth chain (preserves prior entries)."""
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    existing_entry = sign_delegation(root_priv, root_did, sender_agent.did, ["*"])

    task = TaskEnvelope(
        intent=Intent(type="test", params={}),
        auth_chain=[existing_entry],
    )
    with patch.object(sender_agent._transport, "send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "ok"}
        await sender_agent.delegate(
            task=task,
            target_did=receiver_agent.did,
            endpoint="http://localhost:8101",
        )
    sent_task = mock_send.call_args[0][0]
    assert len(sent_task.auth_chain) == 2
    assert sent_task.auth_chain[0].issuer == root_did
    assert sent_task.auth_chain[1].issuer == sender_agent.did
    assert sent_task.auth_chain[1].subject == receiver_agent.did
