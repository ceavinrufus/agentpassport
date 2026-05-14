"""Tests for signed AgentCard (step 5)."""
import pytest
from agentpassport.identity import (
    did_from_public_key,
    generate_keypair,
    sign_agent_card,
    verify_agent_card,
)
from agentpassport.types.agent_card import AgentCard


def _make_card(did: str) -> AgentCard:
    return AgentCard(
        did=did,
        name="Test Agent",
        capabilities=["search", "summarize"],
        endpoint="http://localhost:9000",
    )


# ---------------------------------------------------------------------------
# canonical_payload determinism
# ---------------------------------------------------------------------------

def test_canonical_payload_is_deterministic():
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = _make_card(did)
    assert card.canonical_payload() == card.canonical_payload()


def test_canonical_payload_excludes_signature_field():
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = _make_card(did)
    unsigned_payload = card.canonical_payload()
    signed_card = card.model_copy(update={"signature": "aabbcc"})
    assert signed_card.canonical_payload() == unsigned_payload


def test_canonical_payload_excludes_mutable_metadata():
    """version, cost, latency_p99_ms, schemas must not affect the payload."""
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card_a = AgentCard(did=did, name="A", capabilities=["x"], endpoint="http://a", version="1.0")
    card_b = AgentCard(did=did, name="A", capabilities=["x"], endpoint="http://a", version="9.9")
    assert card_a.canonical_payload() == card_b.canonical_payload()


def test_canonical_payload_changes_on_core_field_change():
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card_a = AgentCard(did=did, name="AgentA", capabilities=["search"], endpoint="http://a")
    card_b = AgentCard(did=did, name="AgentB", capabilities=["search"], endpoint="http://a")
    assert card_a.canonical_payload() != card_b.canonical_payload()


def test_canonical_payload_capabilities_order_independent():
    """Capabilities are sorted before hashing — order must not matter."""
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card_a = AgentCard(did=did, name="A", capabilities=["search", "summarize"], endpoint="http://a")
    card_b = AgentCard(did=did, name="A", capabilities=["summarize", "search"], endpoint="http://a")
    assert card_a.canonical_payload() == card_b.canonical_payload()


# ---------------------------------------------------------------------------
# sign_agent_card / verify_agent_card
# ---------------------------------------------------------------------------

def test_sign_and_verify_round_trip():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = _make_card(did)

    signed = sign_agent_card(card, priv)
    assert signed.signature is not None
    assert verify_agent_card(signed, pub)


def test_verify_fails_on_unsigned_card():
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = _make_card(did)  # no signature
    assert not verify_agent_card(card, pub)


def test_verify_fails_on_tampered_name():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = _make_card(did)
    signed = sign_agent_card(card, priv)
    tampered = signed.model_copy(update={"name": "EvilAgent"})
    assert not verify_agent_card(tampered, pub)


def test_verify_fails_on_wrong_public_key():
    priv, pub = generate_keypair()
    _, other_pub = generate_keypair()
    did = did_from_public_key(pub)
    signed = sign_agent_card(_make_card(did), priv)
    assert not verify_agent_card(signed, other_pub)


# ---------------------------------------------------------------------------
# Registry integration — publish_agent rejects invalid signature
# ---------------------------------------------------------------------------

from agentpassport_registry.app import create_app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=str(tmp_path / "test.db"))


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_registry_accepts_unsigned_card(client):
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    resp = await client.post("/v1/agents", json={
        "did": did, "name": "A", "capabilities": ["x"], "endpoint": "http://a",
    })
    assert resp.status_code == 201


async def test_registry_accepts_valid_signed_card(client):
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = AgentCard(did=did, name="A", capabilities=["x"], endpoint="http://a")
    signed = sign_agent_card(card, priv)
    resp = await client.post("/v1/agents", json=signed.model_dump())
    assert resp.status_code == 201


async def test_registry_rejects_invalid_signature(client):
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = AgentCard(did=did, name="A", capabilities=["x"], endpoint="http://a")
    signed = sign_agent_card(card, priv)
    # Tamper the card after signing
    tampered = signed.model_copy(update={"name": "Evil"})
    resp = await client.post("/v1/agents", json=tampered.model_dump())
    assert resp.status_code == 422


async def test_registry_rejects_garbage_signature(client):
    _, pub = generate_keypair()
    did = did_from_public_key(pub)
    card = AgentCard(did=did, name="A", capabilities=["x"], endpoint="http://a",
                     signature="deadbeef" * 8)
    resp = await client.post("/v1/agents", json=card.model_dump())
    assert resp.status_code == 422
