"""Tests for pre-execution scope declaration (step 4).

Covers: @agent.capability(requires=[...]), TrustMiddleware.check(),
ScopeError raised before handler runs, wildcard scope, empty chain
failure, and backward compat for capabilities with no requires.
"""
import pytest
from agentpassport.agent import Agent
from agentpassport.identity import generate_keypair, did_from_public_key, sign_delegation
from agentpassport.trust import ScopeError, TrustMiddleware
from agentpassport.types.task import TaskEnvelope, Intent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_with_trusted_sender():
    """Return (agent, sender_priv, sender_did) with sender trusted by agent."""
    agent = Agent(name="test-agent")
    sender_priv, sender_pub = generate_keypair()
    sender_did = did_from_public_key(sender_pub)
    agent.trust_keys({sender_did: sender_pub})
    return agent, sender_priv, sender_did


# ---------------------------------------------------------------------------
# Decorator registration
# ---------------------------------------------------------------------------

def test_capability_without_requires_registers_no_scope():
    agent = Agent(name="a")

    @agent.capability("search")
    async def handle(task): return {}

    assert "search" in agent.capabilities
    assert "search" not in agent._capability_scopes


def test_capability_with_requires_stores_scope():
    agent = Agent(name="a")

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {}

    assert agent._capability_scopes["query"] == ["read:db:customers"]


# ---------------------------------------------------------------------------
# TrustMiddleware.check() unit tests
# ---------------------------------------------------------------------------

def test_no_requires_always_passes():
    mw = TrustMiddleware(
        agent_did="did:key:z1",
        known_public_keys={},
        capability_scopes={},  # no scopes registered
    )
    # should not raise regardless of chain
    mw.check(task_auth_chain=[], capability_name="anything")


def test_requires_with_empty_chain_raises():
    mw = TrustMiddleware(
        agent_did="did:key:z1",
        known_public_keys={},
        capability_scopes={"query": ["read:db:customers"]},
    )
    with pytest.raises(ScopeError, match="no auth chain"):
        mw.check(task_auth_chain=[], capability_name="query")


def test_wildcard_scope_covers_any_requirement():
    agent, sender_priv, sender_did = _make_agent_with_trusted_sender()

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {}

    token = sign_delegation(sender_priv, sender_did, agent.did, ["*"])
    # Should not raise
    agent._trust_middleware.check([token], "query")


def test_exact_scope_match_passes():
    agent, sender_priv, sender_did = _make_agent_with_trusted_sender()

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {}

    token = sign_delegation(sender_priv, sender_did, agent.did, ["read:db:customers"])
    agent._trust_middleware.check([token], "query")  # no raise


def test_missing_scope_raises():
    agent, sender_priv, sender_did = _make_agent_with_trusted_sender()

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {}

    token = sign_delegation(sender_priv, sender_did, agent.did, ["write:api:stripe"])
    with pytest.raises(ScopeError, match="read:db:customers"):
        agent._trust_middleware.check([token], "query")


def test_untrusted_issuer_treated_as_missing_scope():
    agent = Agent(name="a")  # no trusted keys registered

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {}

    untrusted_priv, _ = generate_keypair()
    _, untrusted_pub = generate_keypair()
    untrusted_did = did_from_public_key(untrusted_pub)
    token = sign_delegation(untrusted_priv, untrusted_did, agent.did, ["read:db:customers"])

    with pytest.raises(ScopeError):
        agent._trust_middleware.check([token], "query")


# ---------------------------------------------------------------------------
# End-to-end through Agent.handle()
# ---------------------------------------------------------------------------

async def test_handle_runs_when_scope_granted():
    agent, sender_priv, sender_did = _make_agent_with_trusted_sender()

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {"rows": 42}

    token = sign_delegation(sender_priv, sender_did, agent.did, ["read:db:customers"])
    task = TaskEnvelope(
        intent=Intent(type="query", params={}),
        auth_chain=[token],
    )
    result = await agent.handle(task)
    assert result == {"rows": 42}


async def test_handle_raises_scope_error_before_handler():
    agent, sender_priv, sender_did = _make_agent_with_trusted_sender()
    handler_called = False

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task):
        nonlocal handler_called
        handler_called = True
        return {}

    token = sign_delegation(sender_priv, sender_did, agent.did, ["write:api:stripe"])
    task = TaskEnvelope(
        intent=Intent(type="query", params={}),
        auth_chain=[token],
    )
    with pytest.raises(ScopeError):
        await agent.handle(task)

    assert not handler_called, "Handler must not run when scope check fails"


async def test_handle_raises_scope_error_on_empty_chain():
    agent, _, _ = _make_agent_with_trusted_sender()

    @agent.capability("query", requires=["read:db:customers"])
    async def handle(task): return {}

    task = TaskEnvelope(intent=Intent(type="query", params={}), auth_chain=[])
    with pytest.raises(ScopeError, match="no auth chain"):
        await agent.handle(task)


async def test_handle_no_requires_passes_without_chain():
    """Backward compat: capability without requires accepts empty chain."""
    agent = Agent(name="a")

    @agent.capability("echo")
    async def handle(task): return {"ok": True}

    task = TaskEnvelope(intent=Intent(type="echo", params={}))
    result = await agent.handle(task)
    assert result == {"ok": True}
