import pytest
import httpx
from aps_sdk import Agent, Intent, TaskEnvelope
from aps_sdk.identity import generate_keypair, did_from_public_key, sign_delegation
from aps_sdk.types.identity import AuthEntry
from aps_sdk.server import create_agent_app


@pytest.fixture
def receiver():
    agent = Agent(name="receiver")

    @agent.capability("echo")
    async def echo(task: TaskEnvelope) -> dict:
        return {"ok": True}

    return agent


async def test_valid_chain_accepted(receiver):
    """Task with valid auth chain and trusted key is accepted."""
    sender_priv, sender_pub = generate_keypair()
    sender_did = did_from_public_key(sender_pub)
    entry = sign_delegation(sender_priv, sender_did, receiver.did, ["*"])

    receiver.trust_keys({sender_did: sender_pub})
    app = create_agent_app(receiver, verify_auth=True)

    task = TaskEnvelope(intent=Intent(type="echo", params={}), auth_chain=[entry])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/aps/tasks", content=task.model_dump_json())
    assert resp.status_code == 200


async def test_bad_signature_rejected(receiver):
    """Task with forged signature returns 403."""
    bad_entry = AuthEntry(
        issuer="did:aps:fake",
        subject=receiver.did,
        scope=["*"],
        issued_at="2026-01-01T00:00:00+00:00",
        expires_at="2099-01-01T00:00:00+00:00",
        sig="aa" * 32,
    )
    app = create_agent_app(receiver, verify_auth=True)

    task = TaskEnvelope(intent=Intent(type="echo", params={}), auth_chain=[bad_entry])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/aps/tasks", content=task.model_dump_json())
    assert resp.status_code == 403


async def test_empty_chain_rejected(receiver):
    """Empty auth chain returns 403 when verify_auth=True."""
    app = create_agent_app(receiver, verify_auth=True)

    task = TaskEnvelope(intent=Intent(type="echo", params={}), auth_chain=[])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/aps/tasks", content=task.model_dump_json())
    assert resp.status_code == 403


async def test_no_verify_accepts_no_chain(receiver):
    """When verify_auth=False (default), tasks without auth chain are accepted."""
    app = create_agent_app(receiver, verify_auth=False)

    task = TaskEnvelope(intent=Intent(type="echo", params={}), auth_chain=[])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/aps/tasks", content=task.model_dump_json())
    assert resp.status_code == 200
