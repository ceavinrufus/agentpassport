"""Tests for scope escalation prevention in verify_auth_chain.

Scope can only narrow across hops — an intermediate agent cannot grant
permissions it was never given.
"""
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation
from agentpassport.identity.signing import verify_auth_chain


def _make_agent():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    return priv, pub, did


def test_scope_escalation_rejected():
    """mid received ['read:db'], tries to grant ['read:db', 'write:db'] — must be rejected."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["read:db", "write:db"])  # escalated

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_scope_invented_out_of_thin_air_rejected():
    """mid received ['read:db'], grants ['admin:*'] which it never had."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["admin:*"])

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_scope_narrowing_accepted():
    """mid received ['read:db', 'write:db'], grants only ['read:db'] — valid narrowing."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db", "write:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["read:db"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_same_scope_passthrough_accepted():
    """mid passes through the exact same scope it received — valid."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["read:db"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_wildcard_in_prev_allows_any_scope():
    """root grants ['*'] to mid — mid can pass any specific scope downstream."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["*"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["read:db", "write:api:stripe"])

    assert verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_introducing_wildcard_rejected():
    """mid received ['read:db'] and re-delegates ['*'] — that widens the grant."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )


def test_wildcard_then_unrelated_scope_via_introduced_star_rejected():
    """['read:db'] → ['*'] → ['admin'] must not verify. '*' is not a free widening."""
    root_priv, root_pub, root_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()
    leaf_priv, leaf_pub, leaf_did = _make_agent()
    _, _, final_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ["*"])
    hop3 = sign_delegation(leaf_priv, leaf_did, final_did, ["admin"])

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2, hop3],
        expected_subject=final_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub, leaf_did: leaf_pub},
    )


def test_wildcard_passthrough_accepted():
    """A hop that received ['*'] may pass ['*'] downstream."""
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


def test_scope_escalation_in_three_hop_chain_rejected():
    """Escalation at the second re-delegation in a 3-hop chain."""
    root_priv, root_pub, root_did = _make_agent()
    a_priv, a_pub, a_did = _make_agent()
    b_priv, b_pub, b_did = _make_agent()
    _, _, leaf_did = _make_agent()

    hop1 = sign_delegation(root_priv, root_did, a_did, ["read:db"])
    hop2 = sign_delegation(a_priv, a_did, b_did, ["read:db"])
    hop3 = sign_delegation(b_priv, b_did, leaf_did, ["read:db", "delete:db"])  # escalated

    assert not verify_auth_chain(
        auth_chain=[hop1, hop2, hop3],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, a_did: a_pub, b_did: b_pub},
    )
