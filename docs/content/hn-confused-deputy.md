# The confused deputy problem in multi-agent systems

Here's a scenario that's easy to build and hard to notice until something breaks.

You're running a research pipeline. Agent A — your orchestrator — delegates a task to Agent B with a signed token scoped to `read:web`. Agent B does its job, then passes that same token to Agent C, a summarizer subagent it spawned. Agent C decides it needs to cache results. It reaches for `write:db`. Nobody stops it.

In pseudocode:

```python
# Agent A delegates to Agent B
token = sign_delegation(scope=["read:web"], subject=agent_b.did)
agent_b.run(task, auth_token=token)

# Agent B, inside its run(), spawns Agent C and forwards the token
# (or its own derived token — doesn't matter, nobody's checking)
agent_c.run(subtask, auth_token=token)

# Agent C checks... nothing. It just acts.
agent_c.write_to_database(results)  # Agent A never authorized this
```

This isn't a hypothetical. It's the default behavior in every major agent framework today.

## Why this happens

LangGraph, CrewAI, AutoGen — they're all great at orchestration. Graph structure, state management, human-in-the-loop checkpoints. But authorization between nodes? That's left to you. And "left to you" in practice means it doesn't happen.

There's no standard for a node to prove what it was authorized to do. When Agent B receives a task from Agent A, there's no signed token saying "A authorized B for exactly this." When B delegates to C, there's no enforcement that C can't exceed what B was given. The trust model is: if you're in the graph, you're trusted.

That's trust by convention, not cryptography.

## This has a name

In 1988, Dennis Ritchie described the *confused deputy problem*: a program that has legitimate authority (like a compiler with write access to billing files) can be tricked by a less-privileged caller into exercising that authority on the caller's behalf.

The deputy isn't malicious. It just doesn't check whether the caller was supposed to have that capability.

In multi-agent systems, every agent is a potential confused deputy. Agent B isn't malicious. It just forwards a token or inherits ambient permissions without asking whether the original delegator intended that. Agent C acts on behalf of a chain that may have already exceeded its mandate three hops back.

The problem scales with the graph. The deeper the delegation chain, the more opportunities for scope to drift.

## The fix: signed delegation chains with scope narrowing

The principle is simple: every delegation hop must be cryptographically signed, and each hop can only grant a subset of what it received. You can't delegate authority you don't have.

With agentpassport:

```python
from agentpassport import Agent, sign_delegation, verify_auth_chain

# Agent A creates its identity
orchestrator = Agent("orchestrator")

# Agent A delegates to Agent B — read:web only
token_a_to_b = sign_delegation(
    issuer_private_key=orchestrator.private_key,
    issuer_did=orchestrator.did,
    subject_did=agent_b.did,
    scope=["read:web"],
    ttl_seconds=3600,
)

# Agent B wants to delegate to Agent C
# It can only grant scope it has — read:web or narrower
token_b_to_c = sign_delegation(
    issuer_private_key=agent_b.private_key,
    issuer_did=agent_b.did,
    subject_did=agent_c.did,
    scope=["read:web"],  # can't add write:db — it would fail verification
    parent_token=token_a_to_b,
    ttl_seconds=1800,
)

# Agent C declares what it needs before acting
@agent_c.capability("cache_results", requires=["write:db"])
async def handle(task):
    ...  # Never reached — scope check fails before this

# Verification catches it
verify_auth_chain(
    auth_chain=[token_a_to_b, token_b_to_c],
    required_scope=["write:db"],
    known_public_keys={orchestrator.did: orchestrator.public_key}
)
# → ScopeError: requires [write:db], granted [read:web]
```

The check happens before the handler runs. No partial state. No cleanup. The agent stops cleanly.

Revocation works the same way — revoke by JTI and any in-flight request using that token fails at the next capability boundary. You don't have to kill the process.

## The broader point

We're in an early phase where agent frameworks are competing on features — graph DSLs, tool registries, streaming outputs. Authorization is treated as someone else's problem. Usually the application developer's. Usually solved with ad-hoc checks or not at all.

That worked when agents were demos. It stops working when they're running in production, delegating across services, acting on behalf of real users with real data.

The confused deputy problem was solved in operating systems by capability-based security: don't rely on identity alone, pass explicit unforgeable tokens for specific resources. We need the same thing for agent graphs. The building blocks (Ed25519 keys, JWTs, did:key DIDs) all exist. They just need to be wired together in a way that agents can actually use.

I built agentpassport to solve this. It's open source, Apache 2.0, and works across Python and TypeScript with no shared infrastructure. If you've hit delegation scope issues in production — or just know you will — I'd love to hear what your setup looks like.

GitHub: https://github.com/ceavinrufus/agentpassport