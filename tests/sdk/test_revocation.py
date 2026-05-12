"""Tests for soft revocation (step 6).

Covers: InMemoryRevocationRegistry, SqliteRevocationRegistry,
and verify_auth_chain rejecting revoked jtis.
"""
import pytest
from agentpassport.identity import generate_keypair, did_from_public_key, sign_delegation
from agentpassport.identity.signing import verify_auth_chain, _decode_jwt_claims
from agentpassport.revocation import (
    InMemoryRevocationRegistry,
    SqliteRevocationRegistry,
)


# ---------------------------------------------------------------------------
# InMemoryRevocationRegistry
# ---------------------------------------------------------------------------

def test_in_memory_revoke_and_check():
    registry = InMemoryRevocationRegistry()
    assert not registry.is_revoked("abc-jti")
    registry.revoke("abc-jti")
    assert registry.is_revoked("abc-jti")


def test_in_memory_revoke_is_idempotent():
    registry = InMemoryRevocationRegistry()
    registry.revoke("jti-1")
    registry.revoke("jti-1")  # second call must not raise
    assert registry.is_revoked("jti-1")


def test_in_memory_independent_jtis():
    registry = InMemoryRevocationRegistry()
    registry.revoke("jti-a")
    assert not registry.is_revoked("jti-b")


# ---------------------------------------------------------------------------
# SqliteRevocationRegistry
# ---------------------------------------------------------------------------

def test_sqlite_revoke_and_check(tmp_path):
    registry = SqliteRevocationRegistry(str(tmp_path / "rev.db"))
    registry.initialize()
    assert not registry.is_revoked("abc-jti")
    registry.revoke("abc-jti")
    assert registry.is_revoked("abc-jti")


def test_sqlite_revoke_is_idempotent(tmp_path):
    registry = SqliteRevocationRegistry(str(tmp_path / "rev.db"))
    registry.initialize()
    registry.revoke("jti-1")
    registry.revoke("jti-1")
    assert registry.is_revoked("jti-1")


def test_sqlite_persists_across_instances(tmp_path):
    db_path = str(tmp_path / "rev.db")
    r1 = SqliteRevocationRegistry(db_path)
    r1.initialize()
    r1.revoke("persistent-jti")

    r2 = SqliteRevocationRegistry(db_path)
    r2.initialize()
    assert r2.is_revoked("persistent-jti")


def test_sqlite_raises_without_initialize(tmp_path):
    registry = SqliteRevocationRegistry(str(tmp_path / "rev.db"))
    with pytest.raises(RuntimeError, match="initialize"):
        registry.is_revoked("anything")


# ---------------------------------------------------------------------------
# verify_auth_chain with revocation_registry
# ---------------------------------------------------------------------------

def _make_chain():
    """Return (token, sender_did, sender_pub, receiver_did)."""
    sender_priv, sender_pub = generate_keypair()
    sender_did = did_from_public_key(sender_pub)
    _, receiver_pub = generate_keypair()
    receiver_did = did_from_public_key(receiver_pub)
    token = sign_delegation(sender_priv, sender_did, receiver_did, ["read:db:customers"])
    return token, sender_did, sender_pub, receiver_did


def test_verify_passes_without_revocation_registry():
    token, sender_did, sender_pub, receiver_did = _make_chain()
    assert verify_auth_chain(
        auth_chain=[token],
        expected_subject=receiver_did,
        known_public_keys={sender_did: sender_pub},
        revocation_registry=None,
    )


def test_verify_passes_when_jti_not_revoked():
    token, sender_did, sender_pub, receiver_did = _make_chain()
    registry = InMemoryRevocationRegistry()
    assert verify_auth_chain(
        auth_chain=[token],
        expected_subject=receiver_did,
        known_public_keys={sender_did: sender_pub},
        revocation_registry=registry,
    )


def test_verify_fails_when_jti_revoked():
    token, sender_did, sender_pub, receiver_did = _make_chain()
    jti = _decode_jwt_claims(token)["jti"]

    registry = InMemoryRevocationRegistry()
    registry.revoke(jti)

    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=receiver_did,
        known_public_keys={sender_did: sender_pub},
        revocation_registry=registry,
    )


def test_verify_fails_only_revoked_token_in_multi_hop():
    """In a two-hop chain, revoking the first hop must fail the whole chain."""
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    mid_priv, mid_pub = generate_keypair()
    mid_did = did_from_public_key(mid_pub)
    _, recv_pub = generate_keypair()
    recv_did = did_from_public_key(recv_pub)

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"])
    hop2 = sign_delegation(mid_priv, mid_did, recv_did, ["*"])

    registry = InMemoryRevocationRegistry()
    registry.revoke(_decode_jwt_claims(hop1)["jti"])  # revoke the first hop

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=recv_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
        revocation_registry=registry,
    )


def test_verify_with_sqlite_registry(tmp_path):
    token, sender_did, sender_pub, receiver_did = _make_chain()
    jti = _decode_jwt_claims(token)["jti"]

    registry = SqliteRevocationRegistry(str(tmp_path / "rev.db"))
    registry.initialize()
    registry.revoke(jti)

    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=receiver_did,
        known_public_keys={sender_did: sender_pub},
        revocation_registry=registry,
    )
