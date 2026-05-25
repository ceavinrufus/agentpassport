"""Tests for scope escalation prevention in TrustMiddleware.

TrustMiddleware._chain_granted_scopes was computing a union of scopes
across all tokens — meaning an intermediate agent could escalate scope
and TrustMiddleware would accept it.

The fix: scope is intersected (narrowed) across hops, not unioned.
"""
import pytest
from agentpassport.agent import Agent
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation
from agentpassport.trust import ScopeError
from agentpassport.types.task import Intent, TaskEnvelope


def _make_agent():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    return priv, pub, did


def _make_leaf_agent_with_trusted(orchestrator_pub, orchestrator_did, mid_pub, mid_did):
    agent = Agent(name="leaf")
    agent.trust_keys({orchestrator_did: orchestrator_pub, mid_did: mid_pub})
    return agent


async def test_middleware_rejects_escalated_scope_in_chain():
    """orchestrator grants ['read:db'] to mid.
    mid re-delegates ['read:db', 'admin:*'] to leaf — escalation.
    TrustMiddleware on leaf must reject when 'admin:*' is required.
    """
    orch_priv, orch_pub, orch_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()

    leaf = _make_leaf_agent_with_trusted(orch_pub, orch_did, mid_pub, mid_did)

    @leaf.capability("sensitive-op", requires=["admin:*"])
    async def handle(task):
        return {"ok": True}

    hop1 = sign_delegation(orch_priv, orch_did, mid_did, ["read:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf.did, ["read:db", "admin:*"])

    task = TaskEnvelope(
        intent=Intent(type="sensitive-op", params={}),
        auth_chain=[hop1, hop2],
    )
    with pytest.raises(ScopeError):
        await leaf.handle(task)


async def test_middleware_accepts_narrowed_scope():
    """orchestrator grants ['read:db', 'write:db'] to mid.
    mid re-delegates ['read:db'] (narrowed) to leaf.
    leaf requires ['read:db'] — should pass.
    """
    orch_priv, orch_pub, orch_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()

    leaf = _make_leaf_agent_with_trusted(orch_pub, orch_did, mid_pub, mid_did)

    @leaf.capability("read-op", requires=["read:db"])
    async def handle(task):
        return {"rows": 10}

    hop1 = sign_delegation(orch_priv, orch_did, mid_did, ["read:db", "write:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf.did, ["read:db"])

    task = TaskEnvelope(
        intent=Intent(type="read-op", params={}),
        auth_chain=[hop1, hop2],
    )
    result = await leaf.handle(task)
    assert result == {"rows": 10}


async def test_middleware_rejects_when_narrowing_drops_required_scope():
    """orchestrator grants ['read:db', 'write:db'] to mid.
    mid narrows to ['read:db'] when delegating to leaf.
    leaf requires ['write:db'] — must be rejected since mid dropped it.
    """
    orch_priv, orch_pub, orch_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()

    leaf = _make_leaf_agent_with_trusted(orch_pub, orch_did, mid_pub, mid_did)

    @leaf.capability("write-op", requires=["write:db"])
    async def handle(task):
        return {"ok": True}

    hop1 = sign_delegation(orch_priv, orch_did, mid_did, ["read:db", "write:db"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf.did, ["read:db"])  # dropped write:db

    task = TaskEnvelope(
        intent=Intent(type="write-op", params={}),
        auth_chain=[hop1, hop2],
    )
    with pytest.raises(ScopeError):
        await leaf.handle(task)


async def test_middleware_wildcard_in_chain_allows_specific_scope():
    """orchestrator grants ['*'] to mid.
    mid delegates ['read:db'] to leaf.
    leaf requires ['read:db'] — should pass.
    """
    orch_priv, orch_pub, orch_did = _make_agent()
    mid_priv, mid_pub, mid_did = _make_agent()

    leaf = _make_leaf_agent_with_trusted(orch_pub, orch_did, mid_pub, mid_did)

    @leaf.capability("read-op", requires=["read:db"])
    async def handle(task):
        return {"ok": True}

    hop1 = sign_delegation(orch_priv, orch_did, mid_did, ["*"])
    hop2 = sign_delegation(mid_priv, mid_did, leaf.did, ["read:db"])

    task = TaskEnvelope(
        intent=Intent(type="read-op", params={}),
        auth_chain=[hop1, hop2],
    )
    result = await leaf.handle(task)
    assert result == {"ok": True}
