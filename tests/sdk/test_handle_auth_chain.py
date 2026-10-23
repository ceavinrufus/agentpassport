"""Regression tests: Agent.handle must apply verify_auth_chain rules.

Capabilities that declare requires must reject:
- a token whose subject is not the receiving agent
- a chain with an issuer/subject gap between hops
- a chain that widens scope, even when the required scope is on every hop
"""

import pytest
from agentpassport.agent import Agent
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation
from agentpassport.trust import ScopeError
from agentpassport.types.task import Intent, TaskEnvelope


def _party():
    priv, pub = generate_keypair()
    return priv, pub, did_from_public_key(pub)


def _task(capability: str, auth_chain: list[str]) -> TaskEnvelope:
    return TaskEnvelope(intent=Intent(type=capability, params={}), auth_chain=auth_chain)


async def test_handle_rejects_token_addressed_to_another_agent():
    """A trusted issuer's grant to agent A must not authorize agent B.

    The scope string matches the capability. The only defect is sub.
    """
    receiver = Agent(name="receiver")
    issuer_priv, issuer_pub, issuer_did = _party()
    _, _, other_did = _party()
    receiver.trust_keys({issuer_did: issuer_pub})

    called = False

    @receiver.capability("query", requires=["read:db"])
    async def handle(task):
        nonlocal called
        called = True
        return {"ok": True}

    token = sign_delegation(issuer_priv, issuer_did, other_did, ["read:db"])
    with pytest.raises(ScopeError):
        await receiver.handle(_task("query", [token]))
    assert not called


async def test_handle_rejects_issuer_subject_discontinuity():
    """hop1: root→B and hop2: C→receiver (C ≠ B) must be rejected.

    Both issuers are trusted and both hops grant the required scope, so a
    per-token scope union or intersection would still authorize the call.
    """
    receiver = Agent(name="receiver")
    root_priv, root_pub, root_did = _party()
    _, _, skipped_did = _party()
    other_priv, other_pub, other_did = _party()
    receiver.trust_keys({root_did: root_pub, other_did: other_pub})

    called = False

    @receiver.capability("query", requires=["read:db"])
    async def handle(task):
        nonlocal called
        called = True
        return {"ok": True}

    hop1 = sign_delegation(root_priv, root_did, skipped_did, ["read:db"])
    hop2 = sign_delegation(other_priv, other_did, receiver.did, ["read:db"])
    with pytest.raises(ScopeError):
        await receiver.handle(_task("query", [hop1, hop2]))
    assert not called


async def test_handle_rejects_widened_scope_even_if_required_scope_survives():
    """mid received ['read:db'] and re-delegates ['read:db', 'write:db'].

    The capability only requires 'read:db', which appears on both hops.
    The chain is still rejected because scope widened.
    """
    receiver = Agent(name="receiver")
    root_priv, root_pub, root_did = _party()
    mid_priv, mid_pub, mid_did = _party()
    receiver.trust_keys({root_did: root_pub, mid_did: mid_pub})

    called = False

    @receiver.capability("query", requires=["read:db"])
    async def handle(task):
        nonlocal called
        called = True
        return {"ok": True}

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, receiver.did, ["read:db", "write:db"])
    with pytest.raises(ScopeError):
        await receiver.handle(_task("query", [hop1, hop2]))
    assert not called


async def test_handle_rejects_introduced_wildcard():
    """['read:db'] followed by ['*'] is a widening and must not authorize 'admin'."""
    receiver = Agent(name="receiver")
    root_priv, root_pub, root_did = _party()
    mid_priv, mid_pub, mid_did = _party()
    receiver.trust_keys({root_did: root_pub, mid_did: mid_pub})

    called = False

    @receiver.capability("query", requires=["admin"])
    async def handle(task):
        nonlocal called
        called = True
        return {"ok": True}

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, receiver.did, ["*"])
    with pytest.raises(ScopeError):
        await receiver.handle(_task("query", [hop1, hop2]))
    assert not called


async def test_handle_accepts_continuous_narrowed_chain():
    """root→mid→receiver with a narrowed scope still runs the handler."""
    receiver = Agent(name="receiver")
    root_priv, root_pub, root_did = _party()
    mid_priv, mid_pub, mid_did = _party()
    receiver.trust_keys({root_did: root_pub, mid_did: mid_pub})

    @receiver.capability("query", requires=["read:db"])
    async def handle(task):
        return {"rows": 1}

    hop1 = sign_delegation(root_priv, root_did, mid_did, ["read:db", "write:db"])
    hop2 = sign_delegation(mid_priv, mid_did, receiver.did, ["read:db"])
    result = await receiver.handle(_task("query", [hop1, hop2]))
    assert result == {"rows": 1}
