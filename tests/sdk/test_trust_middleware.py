"""Tests for auth chain verification (formerly test_trust_middleware).

server.py / create_agent_app removed in step 3. These tests verify the
underlying verify_auth_chain logic directly — same coverage intent, no
HTTP server dependency.
"""
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation
from agentpassport.identity.signing import verify_auth_chain


def _make_agent_did():
    _, pub = generate_keypair()
    return did_from_public_key(pub), pub


def test_valid_chain_accepted():
    """Valid JWT signed by trusted key is accepted."""
    sender_priv, sender_pub = generate_keypair()
    sender_did = did_from_public_key(sender_pub)
    _, receiver_pub = generate_keypair()
    receiver_did = did_from_public_key(receiver_pub)

    token = sign_delegation(sender_priv, sender_did, receiver_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[token],
        expected_subject=receiver_did,
        known_public_keys={sender_did: sender_pub},
    )


def test_untrusted_key_rejected():
    """JWT signed by a key not in known_public_keys is rejected."""
    untrusted_priv, untrusted_pub = generate_keypair()
    untrusted_did = did_from_public_key(untrusted_pub)
    _, receiver_pub = generate_keypair()
    receiver_did = did_from_public_key(receiver_pub)

    token = sign_delegation(untrusted_priv, untrusted_did, receiver_did, ["*"])

    # Empty trusted key set — issuer not registered
    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=receiver_did,
        known_public_keys={},
    )


def test_empty_chain_rejected():
    """Empty auth chain always returns False."""
    assert not verify_auth_chain(
        auth_chain=[],
        expected_subject="did:key:zanything",
        known_public_keys={},
    )


def test_multi_hop_chain_accepted():
    """Two-hop chain: root → sender → receiver, all trusted."""
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    sender_priv, sender_pub = generate_keypair()
    sender_did = did_from_public_key(sender_pub)
    _, receiver_pub = generate_keypair()
    receiver_did = did_from_public_key(receiver_pub)

    hop1 = sign_delegation(root_priv, root_did, sender_did, ["*"])
    hop2 = sign_delegation(sender_priv, sender_did, receiver_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=receiver_did,
        known_public_keys={root_did: root_pub, sender_did: sender_pub},
    )


def test_wrong_subject_rejected():
    """Chain with correct signature but wrong final subject is rejected."""
    sender_priv, sender_pub = generate_keypair()
    sender_did = did_from_public_key(sender_pub)
    _, receiver_pub = generate_keypair()
    receiver_did = did_from_public_key(receiver_pub)
    _, other_pub = generate_keypair()
    other_did = did_from_public_key(other_pub)

    token = sign_delegation(sender_priv, sender_did, receiver_did, ["*"])

    assert not verify_auth_chain(
        auth_chain=[token],
        expected_subject=other_did,  # wrong subject
        known_public_keys={sender_did: sender_pub},
    )
