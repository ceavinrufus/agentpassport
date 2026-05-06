from aps_sdk.identity.did import generate_keypair, did_from_public_key, parse_did
from aps_sdk.identity.signing import sign_delegation, verify_auth_chain
from aps_sdk.types import AuthEntry


def test_generate_keypair():
    private_key, public_key = generate_keypair()
    assert len(private_key) == 64  # Ed25519 secret key (seed + public)
    assert len(public_key) == 32


def test_did_from_public_key():
    _, public_key = generate_keypair()
    did = did_from_public_key(public_key)
    assert did.startswith("did:aps:")
    assert len(did) > 20


def test_sign_and_verify_single_hop():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()

    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    entry = sign_delegation(
        issuer_private_key=priv_a,
        issuer_did=did_a,
        subject_did=did_b,
        scope=["search"],
        ttl_seconds=3600,
    )
    assert entry.issuer == did_a
    assert entry.subject == did_b

    is_valid = verify_auth_chain(
        auth_chain=[entry],
        expected_subject=did_b,
        known_public_keys={did_a: pub_a},
    )
    assert is_valid is True


def test_verify_fails_on_tampered_scope():
    priv_a, pub_a = generate_keypair()
    _, pub_b = generate_keypair()

    did_a = did_from_public_key(pub_a)
    did_b = did_from_public_key(pub_b)

    entry = sign_delegation(
        issuer_private_key=priv_a,
        issuer_did=did_a,
        subject_did=did_b,
        scope=["search"],
        ttl_seconds=3600,
    )
    # Tamper with scope
    entry.scope = ["search", "delete"]

    is_valid = verify_auth_chain(
        auth_chain=[entry],
        expected_subject=did_b,
        known_public_keys={did_a: pub_a},
    )
    assert is_valid is False
