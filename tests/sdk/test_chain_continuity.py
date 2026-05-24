"""Tests for delegation chain continuity enforcement.

The iss of each token must equal the sub of the previous token.
Passing unrelated tokens as a multi-hop chain must be rejected.
"""
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation
from agentpassport.identity.signing import verify_auth_chain


def _make_agent():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    return priv, pub, did


def test_broken_chain_unrelated_tokens_rejected():
    """hop1: root→B, hop2: C→D (C ≠ B) — chain is broken, must be rejected."""
    root_priv, root_pub, root_did = _make_agent()
    _, b_pub, b_did = _make_agent()
    c_priv, c_pub, c_did = _make_agent()
    _, _, d_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, b_did, ["*"])
    hop2 = sign_delegation(c_priv, c_did, d_did, ["*"])  # C is not B

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=d_did,
        known_public_keys={root_did: root_pub, c_did: c_pub},
    )


def test_broken_chain_middle_gap_rejected():
    """Three tokens where hop2 issuer doesn't match hop1 subject."""
    root_priv, root_pub, root_did = _make_agent()
    _, b_pub, b_did = _make_agent()
    c_priv, c_pub, c_did = _make_agent()  # not B
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, b_did, ["*"])
    hop2 = sign_delegation(c_priv, c_did, mid_did, ["*"])  # gap: C ≠ B
    hop3 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2, hop3],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, c_did: c_pub, mid_did: mid_pub},
    )


def test_valid_two_hop_chain_accepted():
    """root→mid→leaf with correct continuity is accepted."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_valid_three_hop_chain_accepted():
    """root→a→b→leaf with correct continuity is accepted."""
    root_priv, root_pub, root_did = _make_agent()
    a_priv, a_pub, a_did = _make_agent()
    b_priv, b_pub, b_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, a_did, ["*"])
    hop2 = sign_delegation(a_priv, a_did, b_did, ["*"])
    hop3 = sign_delegation(b_priv, b_did, leaf_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2, hop3],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, a_did: a_pub, b_did: b_pub},
    )


def test_single_hop_unaffected():
    """Single-hop chain has no previous token to check continuity against — still works."""
    root_priv, root_pub, root_did = _make_agent()
    _, _, leaf_did = _make_agent()

    token = sign_delegation(root_priv, root_did, leaf_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[token],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub},
    )
