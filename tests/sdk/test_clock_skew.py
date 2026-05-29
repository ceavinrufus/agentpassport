"""Tests for clock skew leeway on iat in verify_auth_chain."""
from __future__ import annotations

import time
import uuid

from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.identity.signing import _encode_jwt, verify_auth_chain


def _make_token(
    priv: bytes, issuer_did: str, subject_did: str, iat_offset: int = 0, ttl: int = 300
) -> str:
    now = int(time.time()) + iat_offset
    claims = {
        "iss": issuer_did,
        "sub": subject_did,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        "scope": ["*"],
        "max_delegations": 0,
    }
    return _encode_jwt(claims, priv[:32])


def test_iat_within_leeway_accepted():
    """Token with iat 15s in the future should be accepted (within 30s leeway)."""
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    token = _make_token(priv, did, did, iat_offset=15)
    result = verify_auth_chain(
        auth_chain=[token],
        expected_subject=did,
        known_public_keys={did: pub},
    )
    assert result is True


def test_iat_outside_leeway_rejected():
    """Token with iat 60s in the future should be rejected (exceeds 30s leeway)."""
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    token = _make_token(priv, did, did, iat_offset=60)
    result = verify_auth_chain(
        auth_chain=[token],
        expected_subject=did,
        known_public_keys={did: pub},
    )
    assert result is False


def test_exp_is_strict():
    """Expired token (exp in the past) is rejected even if iat is fine."""
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    # iat in past, exp also in past
    token = _make_token(priv, did, did, iat_offset=-400, ttl=-100)
    result = verify_auth_chain(
        auth_chain=[token],
        expected_subject=did,
        known_public_keys={did: pub},
    )
    assert result is False
