# Guide: A2A Integration — Exposing and Delegating via the A2A Protocol

This guide covers how to integrate agentpassport with the [A2A (Agent-to-Agent) protocol](https://github.com/google-a2a/A2A). It walks through two patterns: exposing your agentpassport agent as a standards-compliant A2A server (Pattern B), and calling out to an external A2A agent as a downstream dependency (Pattern A). It then shows how to combine both in a single agent that acts as both a server and a client.

---

## Table of Contents

1. [Background: A2A + agentpassport](#1-background-a2a--agentpassport)
2. [Architecture overview](#2-architecture-overview)
3. [Pattern B: Exposing your agent as an A2A server](#3-pattern-b-exposing-your-agent-as-an-a2a-server)
4. [Pattern A: Delegating to an external A2A agent](#4-pattern-a-delegating-to-an-external-a2a-agent)
5. [Using both together](#5-using-both-together)
6. [Reference: synthesize_a2a_agent_card()](#6-reference-synthesize_a2a_agent_card)

---

## 1. Background: A2A + agentpassport

A2A is a transport and discovery protocol: it defines how agents advertise their capabilities (AgentCard), how clients send tasks (JSON-RPC 2.0 `message/send`), and how they poll for results (`tasks/get`). What A2A does not define is *who is allowed to call what* — there is no built-in authorization model.

agentpassport fills that gap. It provides cryptographic identity (DIDs + Ed25519 keypairs), signed delegation chains, and scope enforcement. When you combine the two:

- A2A handles discovery, transport, and task state.
- agentpassport handles trust: every call carries a signed chain proving who authorized what, and your agent can enforce scopes before executing anything.

The A2A adapter (`agentpassport-adapters`) bridges the two without forcing you to choose sides: vanilla A2A clients can call open capabilities without knowing about agentpassport, while agentpassport-aware clients can attach an auth chain for protected capabilities.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Pattern B: Your agent as an A2A server                         │
│                                                                 │
│  A2A client                                                     │
│    │  POST /  {"method": "message/send", "params": {...}}       │
│    │  Header: X-AgentPassport-Auth-Chain: jwt1, jwt2            │
│    ▼                                                            │
│  A2AServerAdapter (Starlette app)                               │
│    ├── GET /.well-known/agent-card.json  ── synthesize_a2a_agent_card()
│    ├── extract skillId → map to capability name                 │
│    ├── parse auth chain header → attach to TaskEnvelope         │
│    └── agent.handle(envelope)                                   │
│          ├── TrustMiddleware.check() (scope enforcement)        │
│          └── your @agent.capability("name") handler             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Pattern A: Delegating to an external A2A agent                 │
│                                                                 │
│  Your agentpassport agent                                       │
│    │  TaskEnvelope { intent, auth_chain }                       │
│    ▼                                                            │
│  A2AClientAdapter                                               │
│    ├── fetch /.well-known/agent-card.json (cached)              │
│    ├── resolve RPC endpoint from supportedInterfaces            │
│    ├── build JSON-RPC message/send request                      │
│    ├── inject X-AgentPassport-Auth-Chain header                 │
│    ├── POST to remote agent                                     │
│    └── poll tasks/get until terminal state                      │
│          └── return extracted result dict                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Pattern B: Exposing your agent as an A2A server

### Install

```bash
pip install agentpassport agentpassport-adapters starlette uvicorn
# Optional: pip install a2a  — for protobuf-backed serialisation (falls back to hand-rolled JSON-RPC otherwise)
```

### Minimal working example

```python
# a2a_server.py
"""
An agentpassport agent served over A2A.

Exposes two capabilities:
  - search   (open — any caller, no auth chain needed)
  - archive  (protected — requires scope "data:write" in auth chain)

Run: python a2a_server.py
Test: curl http://localhost:8080/.well-known/agent-card.json
"""

import asyncio
import uvicorn

from agentpassport.agent import Agent
from agentpassport.identity.did import generate_keypair
from agentpassport.types import AgentCard, TaskEnvelope
from agentpassport_adapters.a2a import A2AServerAdapter

# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

priv, pub = generate_keypair()
agent = Agent("my-search-agent", private_key=priv)

ENDPOINT = "http://localhost:8080"

# Build the AgentCard that describes this agent
card = AgentCard(
    did=agent.did,
    name="my-search-agent",
    capabilities=["search", "archive"],
    endpoint=ENDPOINT,
)

# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

@agent.capability("search")
async def handle_search(task: TaskEnvelope) -> dict:
    """Open capability — no scope required."""
    query = task.intent.params.get("text", "")
    return {"results": [f"result for: {query}"]}


@agent.capability("archive", requires=["data:write"])
async def handle_archive(task: TaskEnvelope) -> dict:
    """Protected capability — caller must present a delegation granting data:write."""
    item = task.intent.params.get("text", "")
    return {"archived": item, "ok": True}


# ---------------------------------------------------------------------------
# Serve
# ---------------------------------------------------------------------------

server = A2AServerAdapter(
    agent=agent,
    agent_card=card,
    endpoint=ENDPOINT,
)
app = server.build_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

---

### AgentCard synthesis — what fields map where

`A2AServerAdapter` serves the AgentCard at `GET /.well-known/agent-card.json`. It calls `synthesize_a2a_agent_card()` internally to convert your agentpassport `AgentCard` to the A2A wire format.

| agentpassport `AgentCard` field | A2A card field |
|---------------------------------|----------------|
| `name` | `name` |
| `capabilities` (list of strings) | `skills` — each becomes `{"id": cap, "name": cap}` |
| `endpoint` | `supportedInterfaces[0].url` |
| `did` | `x_agentpassport_did` (extension field) |
| `signature` | `x_agentpassport_signature` (extension field, omitted when `None`) |

**`x_agentpassport_did`** is how a receiving agent verifies that the A2A card belongs to an agentpassport identity. It carries the raw DID string (e.g. `did:key:z6Mk...`).

When the `a2a` SDK package is installed, the adapter uses its protobuf types for perfect wire-format fidelity. Without it, a hand-rolled dict with the same JSON structure is returned. Either way, the `x_agentpassport_*` extension fields are present.

You can also call `synthesize_a2a_agent_card()` directly if you want the card dict for other purposes:

```python
from agentpassport_adapters.a2a import synthesize_a2a_agent_card

a2a_card_dict = synthesize_a2a_agent_card(aps_card, endpoint="https://prod.example.com")
```

---

### Skill routing — skillId → capability name

A2A clients identify which capability they want via `skillId` in the message metadata. By default, skillId maps directly to the capability name (identity mapping). You can override this with `skill_map`:

```python
server = A2AServerAdapter(
    agent=agent,
    agent_card=card,
    endpoint=ENDPOINT,
    skill_map={
        "web-search":      "search",    # A2A skill id → agentpassport capability
        "store-document":  "archive",
    },
)
```

**SkillId resolution order:**
1. Check `message.skillId` (top-level field)
2. Check `message.skill_id`
3. Check `message.metadata.skillId`
4. Check `message.metadata.skill_id`
5. If no skillId found and the agent has exactly one capability, route to it automatically.
6. If no skillId found and the agent has multiple capabilities, return a JSON-RPC error.

---

### Auth chain flow

The auth chain travels in the `X-AgentPassport-Auth-Chain` HTTP header as a comma-separated list of JWT strings:

```
X-AgentPassport-Auth-Chain: eyJhbGc..., eyJhbGc...
```

The adapter splits this header on commas, strips whitespace, and attaches the resulting list to `TaskEnvelope.auth_chain`. Your capability handler receives the full envelope — including the chain — for any downstream inspection or forwarding.

Scope enforcement happens automatically via `TrustMiddleware` before your handler runs. If the scope check fails, the adapter catches `ScopeError` and returns a JSON-RPC error response (code `-32000`) instead of a 500.

**Open capabilities** (no `requires=` argument) don't check the auth chain at all — any caller can invoke them.

**Protected capabilities** (`requires=["scope:name"]`) require a valid chain with the named scope. No chain = `ScopeError`.

---

### Vanilla A2A client calling an open capability

No agentpassport setup needed. Standard A2A JSON-RPC 2.0:

```python
# vanilla_client.py
"""
A plain httpx client calling the open 'search' capability.
No X-AgentPassport-Auth-Chain header needed for open capabilities.
"""

import asyncio
import httpx
import uuid


async def main():
    request_body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": "agentpassport tutorial"}],
                "metadata": {"skillId": "search"},
            }
        },
    }

    async with httpx.AsyncClient() as client:
        # Discover the agent
        card_resp = await client.get("http://localhost:8080/.well-known/agent-card.json")
        card = card_resp.json()
        print("Agent:", card["name"])
        print("Skills:", [s["id"] for s in card.get("skills", [])])

        # Call open capability
        resp = await client.post("http://localhost:8080/", json=request_body)
        data = resp.json()

    if "error" in data:
        print("Error:", data["error"]["message"])
    else:
        task = data["result"]["task"]
        result_text = task["status"]["message"]["parts"][0]["text"]
        print("Result:", result_text)


asyncio.run(main())
```

---

### agentpassport-aware client calling a protected capability

```python
# aps_client.py
"""
An agentpassport-aware client calling the protected 'archive' capability.
Must sign a delegation and include it in X-AgentPassport-Auth-Chain.
"""

import asyncio
import httpx
import uuid

from agentpassport.identity.did import generate_keypair, did_from_public_key
from agentpassport.identity.signing import sign_delegation

# The server's DID — get this from the agent card's x_agentpassport_did field
SERVER_DID = "did:key:z6Mk..."  # replace with actual value from /.well-known/agent-card.json


async def main():
    # Caller identity
    priv, pub = generate_keypair()
    caller_did = did_from_public_key(pub)

    # Sign a delegation granting "data:write" to the server agent
    delegation_jwt = sign_delegation(
        issuer_private_key=priv,
        issuer_did=caller_did,
        subject_did=SERVER_DID,
        scope=["data:write"],
        ttl_seconds=300,
    )

    request_body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": "important-document.pdf"}],
                "metadata": {"skillId": "archive"},
            }
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8080/",
            json=request_body,
            headers={"X-AgentPassport-Auth-Chain": delegation_jwt},
        )

    data = resp.json()
    if "error" in data:
        print("Error:", data["error"]["message"])
    else:
        task = data["result"]["task"]
        result_text = task["status"]["message"]["parts"][0]["text"]
        print("Result:", result_text)


asyncio.run(main())
```

**First, get the server DID from the card:**

```python
card = httpx.get("http://localhost:8080/.well-known/agent-card.json").json()
server_did = card["x_agentpassport_did"]
```

---

### Error handling

| Situation | JSON-RPC error code | Message |
|-----------|--------------------|-|
| `ScopeError` (auth check fails) | `-32000` | `"Authorization denied: ..."` |
| Unknown skill / capability | `-32602` | `"Unknown skill '...' (resolved capability: '...'). Registered capabilities: [...]"` |
| No skillId with multiple capabilities | `-32602` | `"No skill id provided and agent has multiple capabilities [...]."` |
| Unknown method (not `message/send`) | `-32601` | `"Method '...' not found. This server supports: message/send"` |
| Invalid JSON body | `-32603` | `"Parse error: request body is not valid JSON"` |

All JSON-RPC errors return HTTP 200 (per JSON-RPC spec) with an `error` key in the body. The exception is a parse error on the request body, which returns HTTP 400.

```python
# Error response shape
{
    "jsonrpc": "2.0",
    "id": "req-1",   # or null if id could not be parsed
    "error": {
        "code": -32000,
        "message": "Authorization denied: Capability 'archive' requires scope ['data:write']"
    }
}
```

---

### Production example with uvicorn

```python
# production_server.py
"""
Production-ready A2A server with uvicorn.
Reads private key from env; sets endpoint from config.
"""

import os
import uvicorn
from agentpassport.agent import Agent
from agentpassport.types import AgentCard, TaskEnvelope
from agentpassport_adapters.a2a import A2AServerAdapter

ENDPOINT = os.environ.get("AGENT_ENDPOINT", "https://agent.example.com")
RAW_KEY = bytes.fromhex(os.environ["AGENT_PRIVATE_KEY_HEX"])  # 64-byte Ed25519 seed+pub

agent = Agent("production-agent", private_key=RAW_KEY)

card = AgentCard(
    did=agent.did,
    name="production-agent",
    capabilities=["search", "archive"],
    endpoint=ENDPOINT,
)


@agent.capability("search")
async def handle_search(task: TaskEnvelope) -> dict:
    return {"results": []}


@agent.capability("archive", requires=["data:write"])
async def handle_archive(task: TaskEnvelope) -> dict:
    return {"ok": True}


server = A2AServerAdapter(agent=agent, agent_card=card, endpoint=ENDPOINT)
app = server.build_app()

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        workers=1,  # agentpassport state is in-process; use 1 worker or external state
    )
```

```bash
AGENT_PRIVATE_KEY_HEX=<hex> AGENT_ENDPOINT=https://agent.example.com python production_server.py
```

---

## 4. Pattern A: Delegating to an external A2A agent

`A2AClientAdapter` implements the agentpassport `Adapter` ABC, letting your agent call out to any A2A-compliant service.

### Minimal working example

```python
# a2a_delegate.py
"""
An agentpassport agent that delegates tasks to a remote A2A agent.
"""

import asyncio

from agentpassport.agent import Agent
from agentpassport.identity.did import generate_keypair
from agentpassport.types import Intent, TaskEnvelope
from agentpassport_adapters.a2a import A2AClientAdapter


async def main():
    priv, pub = generate_keypair()
    agent = Agent("orchestrator", private_key=priv)

    # Point at the remote agent's AgentCard URL
    adapter = A2AClientAdapter(
        agent_card_url="https://remote-agent.example.com/.well-known/agent-card.json",
        timeout=30.0,
    )

    # Build a task to delegate
    task = TaskEnvelope(
        intent=Intent(
            type="search",           # maps to the remote agent's skill id
            params={"text": "agentpassport A2A integration"},
        ),
        auth_chain=[],               # no chain for open capabilities
    )

    result = await adapter.execute(task)
    print("Remote result:", result)


asyncio.run(main())
```

---

### Auth chain injection

When your `TaskEnvelope.auth_chain` is non-empty, the adapter automatically injects it into the outgoing request as `X-AgentPassport-Auth-Chain`:

```python
from agentpassport.identity.signing import sign_delegation
from agentpassport.identity.did import generate_keypair, did_from_public_key

priv, pub = generate_keypair()
my_did = did_from_public_key(pub)

REMOTE_DID = "did:key:z6Mk..."  # from remote agent's card["x_agentpassport_did"]

delegation = sign_delegation(
    issuer_private_key=priv,
    issuer_did=my_did,
    subject_did=REMOTE_DID,
    scope=["data:write"],
    ttl_seconds=300,
)

task = TaskEnvelope(
    intent=Intent(type="archive", params={"text": "doc.pdf"}),
    auth_chain=[delegation],   # injected as X-AgentPassport-Auth-Chain header
)

result = await adapter.execute(task)
```

You can also pass the full existing chain through — for example, forwarding the chain you received from an upstream caller:

```python
@agent.capability("proxy")
async def handle_proxy(task: TaskEnvelope) -> dict:
    # Forward the same auth chain the caller gave us
    downstream_task = TaskEnvelope(
        intent=Intent(type="search", params=task.intent.params),
        auth_chain=task.auth_chain,  # pass-through
    )
    return await adapter.execute(downstream_task)
```

---

### Timeout and polling

`A2AClientAdapter` polls the remote agent via `tasks/get` until the task reaches a terminal state (`TASK_STATE_COMPLETED`, `TASK_STATE_FAILED`, `TASK_STATE_CANCELED`, `TASK_STATE_REJECTED`, or `TASK_STATE_AUTH_REQUIRED`). The poll interval starts at 0.5 s and backs off gently (up to 5 s) to avoid hammering slow agents.

```python
# Tight timeout for fast agents
adapter = A2AClientAdapter(
    agent_card_url="https://fast-agent.example.com/.well-known/agent-card.json",
    timeout=5.0,
)

# Generous timeout for slow, long-running tasks
adapter = A2AClientAdapter(
    agent_card_url="https://slow-agent.example.com/.well-known/agent-card.json",
    timeout=120.0,
)
```

`TimeoutError` is raised if the task doesn't reach a terminal state within the timeout:

```python
try:
    result = await adapter.execute(task)
except TimeoutError as e:
    print(f"Remote agent timed out: {e}")
```

---

### Error handling

| Exception | When |
|-----------|------|
| `TimeoutError` | Task didn't reach terminal state within `timeout` seconds |
| `RuntimeError` | Remote agent returned a JSON-RPC `error` response |
| `RuntimeError` | Task reached `TASK_STATE_FAILED` |
| `RuntimeError` | Agent card is missing the `name` field |
| `RuntimeError` | Agent card response is not valid JSON |
| `httpx.HTTPStatusError` | Agent card fetch returned non-2xx |

```python
import httpx
from agentpassport_adapters.a2a import A2AClientAdapter

adapter = A2AClientAdapter("https://remote.example.com/.well-known/agent-card.json")

try:
    result = await adapter.execute(task)
except TimeoutError as e:
    # Task is stuck — log and bail
    print(f"Timeout: {e}")
except RuntimeError as e:
    # Remote agent returned an error or task failed
    print(f"Remote error: {e}")
except httpx.HTTPStatusError as e:
    # Card fetch failed (404, 500, etc.)
    print(f"Card fetch failed: {e.response.status_code}")
```

The AgentCard is cached after the first successful fetch. Subsequent `execute()` calls on the same adapter instance skip the card request.

---

## 5. Using both together

An agent can simultaneously act as an A2A server (accepting inbound tasks) and delegate outbound tasks to other A2A agents. The auth chain flows through naturally.

```python
# hub_agent.py
"""
Hub agent that:
  - Exposes itself as an A2A server
  - Delegates 'search' to a remote search agent
  - Handles 'summarize' locally

Auth chain is forwarded from inbound caller to the downstream search agent.
"""

import uvicorn
from agentpassport.agent import Agent
from agentpassport.identity.did import generate_keypair
from agentpassport.types import AgentCard, Intent, TaskEnvelope
from agentpassport_adapters.a2a import A2AClientAdapter, A2AServerAdapter

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

priv, pub = generate_keypair()
agent = Agent("hub-agent", private_key=priv)

ENDPOINT = "http://localhost:9000"
SEARCH_AGENT_CARD_URL = "https://search-agent.example.com/.well-known/agent-card.json"

search_adapter = A2AClientAdapter(
    agent_card_url=SEARCH_AGENT_CARD_URL,
    timeout=15.0,
)

card = AgentCard(
    did=agent.did,
    name="hub-agent",
    capabilities=["search", "summarize"],
    endpoint=ENDPOINT,
)

# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

@agent.capability("search")
async def handle_search(task: TaskEnvelope) -> dict:
    """Delegate to the remote search agent, forwarding the caller's auth chain."""
    downstream = TaskEnvelope(
        intent=Intent(type="search", params=task.intent.params),
        auth_chain=task.auth_chain,   # forward the chain from the original caller
    )
    return await search_adapter.execute(downstream)


@agent.capability("summarize", requires=["content:read"])
async def handle_summarize(task: TaskEnvelope) -> dict:
    """Handled locally. Requires content:read scope."""
    text = task.intent.params.get("text", "")
    return {"summary": f"Summary of: {text[:100]}"}


# ---------------------------------------------------------------------------
# Serve
# ---------------------------------------------------------------------------

server = A2AServerAdapter(agent=agent, agent_card=card, endpoint=ENDPOINT)
app = server.build_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
```

**What happens on an inbound `search` call:**

1. A2A client POSTs to `http://localhost:9000/` with `skillId=search`
2. `A2AServerAdapter` parses the auth chain from `X-AgentPassport-Auth-Chain`
3. `agent.handle()` dispatches to `handle_search`
4. `handle_search` wraps the task and calls `search_adapter.execute()`
5. `A2AClientAdapter` injects the same auth chain into the outbound request header
6. The remote search agent receives the full chain and can verify it

---

## 6. Reference: synthesize_a2a_agent_card()

**Module:** `agentpassport_adapters.a2a`

```python
def synthesize_a2a_agent_card(
    aps_card: AgentCard,
    endpoint: str | None = None,
) -> dict[str, Any]
```

Converts an agentpassport `AgentCard` to the A2A wire format dict, ready for `json.dumps` or serving at `/.well-known/agent-card.json`.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `aps_card` | `AgentCard` | The agentpassport card to convert. |
| `endpoint` | `str \| None` | Override the endpoint URL in the output. Defaults to `aps_card.endpoint` when omitted. |

### Returns

`dict[str, Any]` — A2A AgentCard dict. Top-level fields:

| Field | Source |
|-------|--------|
| `name` | `aps_card.name` |
| `description` | Always `""` (A2A requires the field; agentpassport cards have no description) |
| `skills` | One `{"id": cap, "name": cap}` entry per capability in `aps_card.capabilities` |
| `supportedInterfaces` | `[{"url": endpoint}]` if endpoint is non-empty; `[]` otherwise |
| `x_agentpassport_did` | `aps_card.did` |
| `x_agentpassport_signature` | `aps_card.signature` (omitted when `None`) |

When the `a2a` SDK is installed, a protobuf-backed dict is produced for the standard fields; the `x_agentpassport_*` extension fields are overlaid on top in both cases.

### Example

```python
from agentpassport.types import AgentCard
from agentpassport_adapters.a2a import synthesize_a2a_agent_card

card = AgentCard(
    did="did:key:z6MkExample",
    name="my-agent",
    capabilities=["search", "summarize"],
    endpoint="https://agent.example.com",
)

a2a_dict = synthesize_a2a_agent_card(card)
# {
#   "name": "my-agent",
#   "description": "",
#   "skills": [{"id": "search", "name": "search"}, {"id": "summarize", "name": "summarize"}],
#   "supportedInterfaces": [{"url": "https://agent.example.com"}],
#   "x_agentpassport_did": "did:key:z6MkExample"
# }

# Override endpoint for a staging deployment
staging_dict = synthesize_a2a_agent_card(card, endpoint="https://staging.agent.example.com")
```
