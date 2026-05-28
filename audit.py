from agentpassport.identity import generate_keypair, did_from_public_key, sign_delegation
from agentpassport.identity.signing import verify_auth_chain

def test_chain_continuity():
    """Broken chain: two unrelated tokens passed as a multi-hop chain.
    hop1: root → B
    hop2: C → D  (C is NOT B, so chain is broken)
    Should FAIL — but does verify_auth_chain enforce hop-to-hop continuity?
    """
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    _, b_pub = generate_keypair()
    b_did = did_from_public_key(b_pub)
    c_priv, c_pub = generate_keypair()
    c_did = did_from_public_key(c_pub)
    _, d_pub = generate_keypair()
    d_did = did_from_public_key(d_pub)

    hop1 = sign_delegation(root_priv, root_did, b_did, ['*'])
    hop2 = sign_delegation(c_priv, c_did, d_did, ['*'])  # C is not B

    result = verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=d_did,
        known_public_keys={root_did: root_pub, c_did: c_pub},
    )
    status = "PASS" if not result else "BUG"
    print(f"[{status}] Chain continuity (unrelated hops accepted={result})")

def test_scope_escalation():
    """mid only received ['read:db'], but re-delegates ['read:db','write:db'].
    Should FAIL — mid can't grant more than it has.
    """
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    mid_priv, mid_pub = generate_keypair()
    mid_did = did_from_public_key(mid_pub)
    _, leaf_pub = generate_keypair()
    leaf_did = did_from_public_key(leaf_pub)

    hop1 = sign_delegation(root_priv, root_did, mid_did, ['read:db'])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ['read:db', 'write:db'])

    result = verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )
    status = "PASS" if not result else "BUG"
    print(f"[{status}] Scope escalation (escalation accepted={result})")

def test_max_delegations():
    """root signs max_delegations=1 to mid. mid re-delegates to leaf.
    max_delegations=1 means mid can act but cannot delegate further.
    Should FAIL.
    """
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    mid_priv, mid_pub = generate_keypair()
    mid_did = did_from_public_key(mid_pub)
    _, leaf_pub = generate_keypair()
    leaf_did = did_from_public_key(leaf_pub)

    hop1 = sign_delegation(root_priv, root_did, mid_did, ['*'], max_delegations=1)
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ['*'])

    result = verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )
    status = "PASS" if not result else "BUG"
    print(f"[{status}] max_delegations=1 (further delegation accepted={result})")

def test_max_delegations_zero():
    """root signs max_delegations=0 to mid. This means mid CANNOT delegate at all.
    Should FAIL immediately if mid tries.
    """
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    mid_priv, mid_pub = generate_keypair()
    mid_did = did_from_public_key(mid_pub)
    _, leaf_pub = generate_keypair()
    leaf_did = did_from_public_key(leaf_pub)

    hop1 = sign_delegation(root_priv, root_did, mid_did, ['*'], max_delegations=0)
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ['*'])

    result = verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )
    status = "PASS" if not result else "BUG"
    print(f"[{status}] max_delegations=0 (delegation accepted={result})")

def test_iss_sub_chain_link():
    """hop1: root→mid, hop2: mid→leaf.
    Check that iss of hop2 == sub of hop1 is actually enforced.
    We already tested the broken case above, this is the positive case.
    """
    root_priv, root_pub = generate_keypair()
    root_did = did_from_public_key(root_pub)
    mid_priv, mid_pub = generate_keypair()
    mid_did = did_from_public_key(mid_pub)
    _, leaf_pub = generate_keypair()
    leaf_did = did_from_public_key(leaf_pub)

    hop1 = sign_delegation(root_priv, root_did, mid_did, ['*'])
    hop2 = sign_delegation(mid_priv, mid_did, leaf_did, ['*'])

    result = verify_auth_chain(
        auth_chain=[hop1, hop2],
        expected_subject=leaf_did,
        known_public_keys={root_did: root_pub, mid_did: mid_pub},
    )
    status = "PASS" if result else "BUG"
    print(f"[{status}] Valid 2-hop chain accepted={result}")

if __name__ == "__main__":
    test_chain_continuity()
    test_scope_escalation()
    test_max_delegations()
    test_max_delegations_zero()
    test_iss_sub_chain_link()
