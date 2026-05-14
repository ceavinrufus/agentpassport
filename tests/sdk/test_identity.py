import base64
import json

import pytest
from agentpassport.identity.did import did_from_public_key, generate_keypair, parse_did
from agentpassport.identity.signing import (
    _decode_jwt_claims,
    sign_delegation,
    verify_auth_chain,
)

# ---------------------------------------------------------------------------
# DID helpers (carried forward from step 1)
# ---------------------------------------------------------------------------

def test_generate_keypair():
    private_key, public_key = generate_keypair()
    assert len(private_key) == 64  # Ed25519 secret key (seed + public)
    assert len(public_key) == 32


def test_did_from_public_key():
    _, public_key = generate_keypair()
    did = did_from_public_key(public_key)
    assert did.startswith("did:key:z")
    assert len(did) > 20


def test_did_round_trip():
    """Public key must survive a full did_from_public_key → parse_did round-trip."""
    _, public_key = generate_keypair()
    did = did_from_public_key(public_key)
    recovered = parse_did(did)
    assert recovered == public_key


def test_parse_did_rejects_wrong_scheme():
    with pytest.raises(ValueError, match="did:key:z"):
        parse_did("did:invalid:somelegacyvalue")


def test_parse_did_rejects_wrong_multicodec():
    from agentpassport.identity.did import _base58btc_encode
    bad_prefixed = bytes([0xe7, 0x01]) + bytes(33)
    bad_did = f"did:key:z{_base58btc_encode(bad_prefixed)}"
    with pytest.raises(ValueError, match="0xed01"):
        parse_did(bad_did)


# ---------------------------------------------------------------------------
# JWT structure
# ---------------------------------------------------------------------------

def test_sign_delegation_returns_jwt_string():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(priv_a, did_a, did_b, ["read:db:customers"])

    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3, "JWT must have exactly 3 dot-separated parts"


def test_jwt_header_declares_eddsa():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    token = sign_delegation(priv_a, did_from_public_key(pub_a), did_from_public_key(pub_b), ["x"])

    header_part = token.split(".")[0]
    padding = 4 - len(header_part) % 4
    if padding != 4:
        header_part += "=" * padding
    header = json.loads(base64.urlsafe_b64decode(header_part))

    assert header["alg"] == "EdDSA"
    assert header["crv"] == "Ed25519"


def test_jwt_claims_are_correct():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(
        priv_a, did_a, did_b, ["read:db:customers"], ttl_seconds=3600, max_delegations=2
    )
    claims = _decode_jwt_claims(token)

    assert claims["iss"] == did_a
    assert claims["sub"] == did_b
    assert claims["scope"] == ["read:db:customers"]
    assert claims["max_delegations"] == 2
    assert "iat" in claims
    assert "exp" in claims
    assert "jti" in claims
    assert claims["exp"] > claims["iat"]


def test_jwt_jti_is_unique():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    t1 = sign_delegation(priv_a, did_a, did_b, ["x"])
    t2 = sign_delegation(priv_a, did_a, did_b, ["x"])

    assert _decode_jwt_claims(t1)["jti"] != _decode_jwt_claims(t2)["jti"]


# ---------------------------------------------------------------------------
# verify_auth_chain
# ---------------------------------------------------------------------------

def test_sign_and_verify_single_hop():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(priv_a, did_a, did_b, ["search"])

    assert verify_auth_chain(
        auth_chain=[token],
        expected_subject=did_b,
        known_public_keys={did_a: pub_a},
    )


def test_verify_fails_on_tampered_payload():
    """Altering the payload bytes after signing must fail verification."""
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(priv_a, did_a, did_b, ["search"])

    # Swap the payload for a different scope
    header, _, sig = token.split(".")
    tampered_claims = _decode_jwt_claims(token)
    tampered_claims["scope"] = ["search", "delete"]
    tampered_payload = base64.urlsafe_b64encode(
        json.dumps(tampered_claims, separators=(",", ":"), sort_keys=True).encode()
    ).rstrip(b"=").decode()
    tampered_token = f"{header}.{tampered_payload}.{sig}"

    assert not verify_auth_chain(
        auth_chain=[tampered_token],
        expected_subject=did_b,
        known_public_keys={did_a: pub_a},
    )


def test_verify_fails_on_expired_delegation():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(priv_a, did_a, did_b, ["search"], ttl_seconds=-1)

    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=did_b,
        known_public_keys={did_a: pub_a},
    )


def test_verify_fails_on_unknown_issuer():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    token = sign_delegation(priv_a, did_a, did_b, ["search"])

    # Pass an empty known_public_keys — issuer not trusted
    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=did_b,
        known_public_keys={},
    )


def test_verify_fails_on_wrong_expected_subject():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    _, pub_c = generate_keypair()
    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)
    did_c = did_from_public_key(pub_c)

    token = sign_delegation(priv_a, did_a, did_b, ["search"])

    # Expect sub=did_c but token has sub=did_b
    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=did_c,
        known_public_keys={did_a: pub_a},
    )


def test_verify_empty_chain_fails():
    assert not verify_auth_chain(
        auth_chain=[],
        expected_subject="did:key:zanything",
        known_public_keys={},
    )
