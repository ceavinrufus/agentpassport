"""Tests for max_delegations enforcement in verify_auth_chain.

max_delegations=N on a token means the recipient may delegate at most N
further times. max_delegations=0 means the recipient cannot delegate at all.
"""
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation
from agentpassport.identity.signing import verify_auth_chain


def _make_agent():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    return priv, pub, did


def test_max_delegations_minus_one_means_unlimited():
    """max_delegations=-1 is the default and means 'no constraint'.
    A chain where hop1 has max_delegations=-1 and hop2 exists is valid."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"], max_delegations=-1)
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_max_delegations_zero_blocks_any_further_hop():
    """max_delegations=0 means the recipient cannot delegate at all.
    root→mid (max_delegations=0) grants mid no delegation rights.
    A chain where mid then delegates to leaf must be rejected."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"], max_delegations=0)
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_max_delegations_one_blocks_second_hop():
    """root→mid (max_delegations=1)→leaf→deeper: the third hop must be rejected."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    leaf_priv, leaf_pub, leaf_did = _make_agent()
    _, _, deeper_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"], max_delegations=1)
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])
    hop3 = sign_delegation(leaf_priv, leaf_did, deeper_did, ["*"])

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2, hop3],
        expected_subject=deeper_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub, leaf_did: leaf_pub},
    )


def test_max_delegations_one_allows_one_hop():
    """root→mid (max_delegations=1)→leaf: exactly one hop is allowed."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"], max_delegations=1)
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_max_delegations_two_allows_two_hops():
    """root→a (max_delegations=2)→b→c: two further hops allowed."""
    root_priv, root_pub, root_did = _make_agent()
    a_priv, a_pub, a_did = _make_agent()
    b_priv, b_pub, b_did = _make_agent()
    _, _, c_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, a_did, ["*"], max_delegations=2)
    hop2 = sign_delegation(a_priv, a_did, b_did, ["*"])
    hop3 = sign_delegation(b_priv, b_did, c_did, ["*"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2, hop3],
        expected_subject=c_did,
        known_public_keys={root_did: root_pub, a_did: a_pub, b_did: b_pub},
    )


def test_single_hop_with_max_delegations_zero_accepted():
    """A single-token chain where the token itself has max_delegations=0 is fine —
    it just means the recipient can't delegate further. There's no further hop here."""
    root_priv, root_pub, root_did = _make_agent()
    _, _, leaf_did = _make_agent()

    token = sign_delegation(root_priv, root_did, leaf_did, ["*"], max_delegations=0)

    assert verify_auth_chain(
        auth_chain=[token],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub},
    )
