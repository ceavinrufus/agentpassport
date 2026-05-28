"""Tests for authenticated DELETE /v1/agents/{did}."""
from __future__ import annotations

import time

import pytest
from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.identity.signing import _encode_jwt
from agentpassport_registry.app import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=str(tmp_path / "test.db"))


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_delete_proof(
    private_key: bytes, did: str, iat_offset: int = 0, exp_offset: int = 300
) -> str:
    now = int(time.time()) + iat_offset
    claims = {
        "sub": did,
        "action": "delete",
        "iat": now,
        "exp": now + exp_offset,
    }
    return _encode_jwt(claims, private_key[:32])


async def _register_agent(client, did: str) -> None:
    card = {
        "did": did,
        "name": "Test Agent",
        "capabilities": ["test"],
        "endpoint": "http://agent:8000",
    }
    resp = await client.post("/v1/agents", json=card)
    assert resp.status_code == 201


async def test_delete_with_valid_proof(client):
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    await _register_agent(client, did)

    proof = _make_delete_proof(priv, did)
    resp = await client.delete(f"/v1/agents/{did}", headers={"X-Delete-Proof": proof})
    assert resp.status_code == 204

    # confirm it's gone
    resp = await client.get(f"/v1/agents/{did}")
    assert resp.status_code == 404


async def test_delete_missing_proof_returns_401(client):
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    await _register_agent(client, did)

    resp = await client.delete(f"/v1/agents/{did}")
    assert resp.status_code == 401


async def test_delete_wrong_key_returns_401(client):
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    await _register_agent(client, did)

    # sign with a different key
    wrong_priv, _ = generate_keypair()
    proof = _make_delete_proof(wrong_priv, did)
    resp = await client.delete(f"/v1/agents/{did}", headers={"X-Delete-Proof": proof})
    assert resp.status_code == 401


async def test_delete_expired_proof_returns_401(client):
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    await _register_agent(client, did)

    # exp in the past
    proof = _make_delete_proof(priv, did, iat_offset=-400, exp_offset=-100)
    resp = await client.delete(f"/v1/agents/{did}", headers={"X-Delete-Proof": proof})
    assert resp.status_code == 401
