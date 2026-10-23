# LangGraph + agentpassport: Scoped delegation for multi-agent workflows

LangGraph gives you powerful tools for building multi-agent systems: stateful graphs, conditional edges, human-in-the-loop checkpoints, streaming. What it doesn't give you is an authorization layer between nodes.

When one node in your graph calls another — a researcher delegating to a writer, an orchestrator spinning up a subagent — there's no built-in way to say "this node is authorized to do X and only X." Trust flows by convention: if you're in the graph, you can do anything in the graph.

This tutorial shows how to add cryptographic scope enforcement between LangGraph nodes using agentpassport. You'll build a research pipeline where a researcher agent delegates to a writer agent with `read:web` scope only — and see exactly what happens when the writer tries to exceed that scope.

## What we're building

```
[Orchestrator] → delegates(scope=read:web) → [Researcher]
                                                    ↓
                                   delegates(scope=read:web) → [Writer]
                                                                   ↓
                                           attempts write:db → ScopeError ✅
```

The writer can summarize. It cannot persist. The scope is enforced cryptographically before any handler runs.

## Setup

```bash
pip install langgraph agentpassport
```

## The code

```python
import asyncio
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from agentpassport import Agent, sign_delegation, verify_auth_chain, ScopeError
from agentpassport.revocation import InMemoryRevocationRegistry

# --- Agent identities ---

orchestrator = Agent("orchestrator")
researcher = Agent("researcher")
writer = Agent("writer")

# Shared revocation registry (in production, use SqliteRevocationRegistry)
registry = InMemoryRevocationRegistry()

# Researcher trusts orchestrator's keys
researcher_trusted_keys = {orchestrator.did: orchestrator.public_key}

# Writer trusts researcher's keys
writer_trusted_keys = {researcher.did: researcher.public_key}


# --- Graph state ---

class ResearchState(TypedDict):
    topic: str
    auth_token: str        # delegation token passed between nodes
    research_notes: str
    final_article: str
    error: str


# --- Node: Orchestrator ---

def orchestrator_node(state: ResearchState) -> ResearchState:
    """Signs a delegation to the researcher scoped to read:web only."""
    token = sign_delegation(
        issuer_private_key=orchestrator.private_key,
        issuer_did=orchestrator.did,
        subject_did=researcher.did,
        scope=["read:web"],
        ttl_seconds=3600,
        revocation_registry=registry,
    )
    print(f"[Orchestrator] Signed delegation → researcher | scope: read:web")
    return {**state, "auth_token": token}


# --- Node: Researcher ---

def researcher_node(state: ResearchState) -> ResearchState:
    """Verifies its delegation, does research, re-delegates to writer."""
    # Verify the orchestrator's delegation
    try:
        verify_auth_chain(
            auth_chain=[state["auth_token"]],
            expected_subject=researcher.did,
            required_scope=["read:web"],
            known_public_keys=researcher_trusted_keys,
            revocation_registry=registry,
        )
    except ScopeError as e:
        return {**state, "error": f"Researcher auth failed: {e}"}

    print(f"[Researcher] Auth verified ✅ | Fetching web content for: {state['topic']}")

    # Simulate web research (real impl would use a search tool here)
    notes = f"Research notes on '{state['topic']}': [fetched from web, read:web scope used]"

    # Re-delegate to writer — same scope (read:web), narrowed TTL
    writer_token = sign_delegation(
        issuer_private_key=researcher.private_key,
        issuer_did=researcher.did,
        subject_did=writer.did,
        scope=["read:web"],   # can only grant what we have
        ttl_seconds=1800,
        revocation_registry=registry,
    )

    return {**state, "research_notes": notes, "auth_token": writer_token}


# --- Node: Writer ---

def writer_node(state: ResearchState) -> ResearchState:
    """Verifies delegation, writes article. Cannot exceed read:web scope."""
    # Verify the researcher's delegation
    try:
        verify_auth_chain(
            auth_chain=[state["auth_token"]],
            expected_subject=writer.did,
            required_scope=["read:web"],
            known_public_keys=writer_trusted_keys,
            revocation_registry=registry,
        )
    except ScopeError as e:
        return {**state, "error": f"Writer auth failed: {e}"}

    print(f"[Writer] Auth verified ✅ | Writing article from research notes")

    # This works — read:web is granted
    article = f"# Article: {state['topic']}\n\n{state['research_notes']}\n\n[Written by writer agent]"

    # Now let's see what happens if the writer tries to exceed its scope
    print(f"[Writer] Attempting to cache results to database...")
    try:
        verify_auth_chain(
            auth_chain=[state["auth_token"]],
            expected_subject=writer.did,
            required_scope=["write:db"],   # NOT in the delegation chain
            known_public_keys=writer_trusted_keys,
            revocation_registry=registry,
        )
        # This line never runs
        print("[Writer] write:db access granted")
    except ScopeError as e:
        print(f"[Writer] Scope check failed 🛡️ — {e}")
        print("[Writer] Continuing without DB write (correct behavior)")

    return {**state, "final_article": article}


# --- Build the graph ---

def build_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("writer", writer_node)

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", END)

    return graph.compile()


# --- Run it ---

if __name__ == "__main__":
    app = build_graph()

    result = app.invoke({
        "topic": "cryptographic delegation in multi-agent systems",
        "auth_token": "",
        "research_notes": "",
        "final_article": "",
        "error": "",
    })

    print("\n--- Final Output ---")
    if result["error"]:
        print(f"Error: {result['error']}")
    else:
        print(result["final_article"])
```

## Running the example

```bash
python research_pipeline.py
```

Expected output:

```
[Orchestrator] Signed delegation → researcher | scope: read:web
[Researcher] Auth verified ✅ | Fetching web content for: cryptographic delegation in multi-agent systems
[Writer] Auth verified ✅ | Writing article from research notes
[Writer] Attempting to cache results to database...
[Writer] Scope check failed 🛡️ — ScopeError: requires [write:db], granted [read:web]
[Writer] Continuing without DB write (correct behavior)

--- Final Output ---
# Article: cryptographic delegation in multi-agent systems

Research notes on 'cryptographic delegation in multi-agent systems': [fetched from web, read:web scope used]

[Written by writer agent]
```

The writer can read. It cannot write to the database. The scope check happens before the handler runs — no partial state, no cleanup needed.

## What this gives you

- **Auditable delegation chains.** Every hop is a signed JWT. You can trace exactly who authorized what, when, and with what scope.
- **Fail-fast scope enforcement.** Capabilities declare what they need. agentpassport checks before running. Bad requests fail cleanly.
- **Revocation without process kills.** Revoke a delegation by JTI mid-flight. The current action completes; the next one fails.
- **Cross-language.** Your LangGraph orchestrator can delegate to a TypeScript microagent and the same trust chain verifies.

## What's next

- Add `SqliteRevocationRegistry` for persistent revocation across restarts
- Wire in real tool calls (search APIs, database writes) and protect them with capabilities
- Use `agentpassport-adapters` for MCP or A2A protocol integration

---

**agentpassport** — Signed delegation on top of the auth you already have. OAuth and MCP auth decide which client may reach a server. agentpassport records what each agent in the chain was allowed to do.

GitHub: https://github.com/ceavinrufus/agentpassport
Docs: https://agentpassport.fyi