# AgentPassport Registry — API Reference

Complete reference for the `agentpassport-registry` service and its HTTP API.

---

## Table of Contents

- [Overview](#overview)
- [Running the Registry](#running-the-registry)
- [HTTP API](#http-api)
  - [GET /health](#get-health)
  - [POST /v1/agents](#post-v1agents)
  - [GET /v1/agents/query](#get-v1agentsquery)
  - [GET /v1/agents/{did}](#get-v1agentsdid)
  - [DELETE /v1/agents/{did}](#delete-v1agentsdid)
- [Python internals](#python-internals)
  - [Function: `create_app()`](#function-create_app)
  - [Abstract class: `Storage`](#abstract-class-storage)
  - [Class: `SqliteStorage`](#class-sqlitestorage)
  - [Class: `QueryEngine`](#class-queryengine)
- [Rate limiting](#rate-limiting)
- [RegistryClient (Python SDK)](#registryclient-python-sdk)
- [Full integration example](#full-integration-example)

---

## Overview

The AgentPassport Registry is an optional central directory where agents publish their `AgentCard` and orchestrators discover agents by capability. It is a FastAPI service backed by SQLite.

**What it provides:**
- Publish an `AgentCard` (with optional signature verification)
- Look up an agent by DID
- Query agents by capability, cost, and latency constraints
- Ranked results (cheapest first, then by latency)

**What it does NOT provide:**
- Authentication/authorization (use network-level controls or add your own middleware)
- Consensus or federation (single instance)
- Real-time push notifications

---

## Running the Registry

### Install

```bash
pip install agentpassport-registry uvicorn
```

### Start

```bash
uvicorn agentpassport_registry.app:create_app --factory --port 8000
```

Or from Python:

```python
import uvicorn
from agentpassport_registry.app import create_app

app = create_app(db_path="/var/lib/agentpassport/registry.db")
uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Docker (example)

```dockerfile
FROM python:3.12-slim
RUN pip install agentpassport-registry uvicorn
CMD ["uvicorn", "agentpassport_registry.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

---

## HTTP API

All endpoints return JSON. All error responses follow FastAPI's default format:
```json
{"detail": "message or structured object"}
```

---

### GET /health

Check service health.

**Request:** No parameters.

**Response 200:**
```json
{"status": "ok"}
```

**Example:**
```bash
curl http://localhost:8000/health
```

---

### POST /v1/agents

Publish or update an `AgentCard` in the registry.

**Rate limit:** 10 requests per minute per client IP.

**Request body:** `AgentCard` JSON object.

```json
{
  "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "name": "summarizer",
  "version": "1.0.0",
  "capabilities": ["summarize", "extract_keywords"],
  "endpoint": "http://summarizer.internal:8080",
  "cost": {"currency": "credits", "per_task": 2.5},
  "latency_p99_ms": 1500,
  "transports": ["http"],
  "signature": "abc123..."
}
```

**Behavior:**
- If `signature` is `null` or absent: card is accepted without verification.
- If `signature` is present: the registry verifies it against `card.canonical_payload()` using the public key derived from `card.did`. If verification fails, returns 422.
- Uses `INSERT OR REPLACE` — existing entries for the same DID are overwritten.

**Response 201:**
```json
{"status": "registered", "did": "did:key:z6Mk..."}
```

**Response 422 — Invalid DID:**
```json
{"detail": "Invalid DID: Invalid did:key DID (expected did:key:z...): ..."}
```

**Response 422 — Bad signature:**
```json
{"detail": "AgentCard signature verification failed"}
```

**Response 429 — Rate limited:**
```json
{"error": "Rate limit exceeded: 10 per 1 minute"}
```

**Example:**
```bash
curl -X POST http://localhost:8000/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "did": "did:key:z6Mk...",
    "name": "my-agent",
    "capabilities": ["summarize"],
    "endpoint": "http://localhost:8001"
  }'
```

---

### GET /v1/agents/query

Query agents by capability, with optional cost and latency filters.

**Rate limit:** 60 requests per minute per client IP.

**Query parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `capability` | `string` | Yes | — | Capability name to filter by. Only agents with this exact string in their `capabilities` list are returned. |
| `max_cost` | `float` | No | `null` | If provided, exclude agents whose `cost.per_task > max_cost`. |
| `max_latency_ms` | `int` | No | `null` | If provided, exclude agents whose `latency_p99_ms > max_latency_ms`. Agents with no latency info are not excluded. |

**Response 200:** Array of `AgentCard` JSON objects, sorted by `cost.per_task` ascending, then `latency_p99_ms` ascending.

```json
[
  {
    "did": "did:key:z6Mk...",
    "name": "fast-summarizer",
    "capabilities": ["summarize"],
    "cost": {"currency": "credits", "per_task": 1.0},
    "latency_p99_ms": 500,
    "endpoint": "http://fast:8080",
    ...
  },
  {
    "did": "did:key:z6Mk...",
    "name": "good-summarizer",
    "capabilities": ["summarize"],
    "cost": {"currency": "credits", "per_task": 2.5},
    "latency_p99_ms": 1500,
    "endpoint": "http://good:8081",
    ...
  }
]
```

**Example:**
```bash
# Find all agents that can summarize, costing at most 2 credits, within 2 seconds
curl "http://localhost:8000/v1/agents/query?capability=summarize&max_cost=2.0&max_latency_ms=2000"
```

---

### GET /v1/agents/{did}

Look up a specific agent by DID.

**Rate limit:** 60 requests per minute per client IP.

**Path parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `did` | `string` | Yes | The agent's full DID (URL-encoded if necessary). Uses `{did:path}` routing so slashes in the DID are allowed. |

**Response 200:** The `AgentCard` JSON object.

**Response 404:**
```json
{"detail": "Agent not found"}
```

**Example:**
```bash
curl "http://localhost:8000/v1/agents/did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
```

---

### DELETE /v1/agents/{did}

Remove an agent from the registry.

**Note:** No authentication — add your own middleware if you need delete protection.

**Path parameters:** Same as GET.

**Response 204:** No content. Idempotent — deleting a non-existent DID succeeds silently.

**Example:**
```bash
curl -X DELETE "http://localhost:8000/v1/agents/did:key:z6Mk..."
```

---

## Python internals

### Function: `create_app()`

**Module:** `agentpassport_registry.app`

```python
def create_app(db_path: str = "agentpassport_registry.db") -> FastAPI
```

Factory function that creates and configures the FastAPI application.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `"agentpassport_registry.db"` | Path to the SQLite database file. Created if it doesn't exist. |

**Returns:** Configured `FastAPI` instance.

**Side effects:**
- Creates a `SqliteStorage` and calls `initialize()` (creates the table if needed).
- Sets up the rate limiter exception handler.
- Registers the router.

**Example:**
```python
from agentpassport_registry.app import create_app
import uvicorn

# Development
app = create_app()  # in-memory or local db

# Production
app = create_app(db_path="/data/registry.db")
uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### Abstract class: `Storage`

**Module:** `agentpassport_registry.storage.base`

```python
class Storage(ABC):
    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def register(self, card: AgentCard) -> None: ...

    @abstractmethod
    def get(self, did: str) -> AgentCard | None: ...

    @abstractmethod
    def delete(self, did: str) -> None: ...

    @abstractmethod
    def list_all(self) -> list[AgentCard]: ...
```

Abstract base for storage backends. Implement this to use a different database (PostgreSQL, Redis, etc.).

| Method | Description |
|--------|-------------|
| `initialize()` | Create tables/indexes. Called at startup. Safe to call multiple times. |
| `register(card)` | Upsert an agent card. Must be idempotent for the same DID. |
| `get(did)` | Return the `AgentCard` for the given DID, or `None` if not found. |
| `delete(did)` | Remove the card for the given DID. Idempotent. |
| `list_all()` | Return all registered agent cards. |

**Example: Custom storage backend**
```python
from agentpassport_registry.storage.base import Storage
from agentpassport.types import AgentCard

class InMemoryStorage(Storage):
    def __init__(self):
        self._cards: dict[str, AgentCard] = {}

    def initialize(self) -> None:
        pass  # Nothing to do for in-memory

    def register(self, card: AgentCard) -> None:
        self._cards[card.did] = card

    def get(self, did: str) -> AgentCard | None:
        return self._cards.get(did)

    def delete(self, did: str) -> None:
        self._cards.pop(did, None)

    def list_all(self) -> list[AgentCard]:
        return list(self._cards.values())
```

---

### Class: `SqliteStorage`

**Module:** `agentpassport_registry.storage.sqlite`

```python
class SqliteStorage(Storage):
    def __init__(self, db_path: str = "agentpassport_registry.db") -> None
    def initialize(self) -> None
    def register(self, card: AgentCard) -> None
    def get(self, did: str) -> AgentCard | None
    def delete(self, did: str) -> None
    def list_all(self) -> list[AgentCard] -> None
```

SQLite-backed storage. Uses `INSERT OR REPLACE` for upserts. Serializes `AgentCard` as JSON.

**Constructor:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `"agentpassport_registry.db"` | SQLite database file path. |

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS agent_cards (
    did  TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
```

**Thread safety:** Uses `check_same_thread=False`. Safe for single-threaded async use (FastAPI with a single worker). For multi-process deployments, use a separate DB per process or switch to PostgreSQL.

**Example:**
```python
from agentpassport_registry.storage.sqlite import SqliteStorage
from agentpassport.types import AgentCard

storage = SqliteStorage(db_path="/tmp/test.db")
storage.initialize()

card = AgentCard(
    did="did:key:z6Mk...",
    name="test-agent",
    capabilities=["ping"],
    endpoint="http://localhost:8001",
)
storage.register(card)

retrieved = storage.get("did:key:z6Mk...")
assert retrieved is not None
assert retrieved.name == "test-agent"

all_cards = storage.list_all()
print(len(all_cards))  # 1

storage.delete("did:key:z6Mk...")
assert storage.get("did:key:z6Mk...") is None
```

---

### Class: `QueryEngine`

**Module:** `agentpassport_registry.query`

```python
class QueryEngine:
    def query(
        self,
        cards: list[AgentCard],
        capability: str,
        max_cost_per_task: float | None = None,
        max_latency_ms: int | None = None,
    ) -> list[AgentCard]
```

Stateless query and ranking engine. Operates on a list of `AgentCard` objects.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cards` | `list[AgentCard]` | Yes | — | All agent cards to filter |
| `capability` | `str` | Yes | — | Exact capability name to match |
| `max_cost_per_task` | `float \| None` | No | `None` | Exclude agents with `cost.per_task > max_cost_per_task` |
| `max_latency_ms` | `int \| None` | No | `None` | Exclude agents with `latency_p99_ms > max_latency_ms`. Agents with `latency_p99_ms = None` are **not** excluded. |

**Returns:** `list[AgentCard]` — filtered and sorted list, cheapest first, then by latency ascending.

**Matching:** `capability` must be an **exact string match** in `card.capabilities`. No partial matching.

**Ranking:**
1. Primary: `cost.per_task` ascending (agents with no cost info rank last with `float("inf")`)
2. Secondary: `latency_p99_ms` ascending (agents with no latency info rank first with `0`)

**Example:**
```python
from agentpassport_registry.query import QueryEngine
from agentpassport.types import AgentCard, CostInfo

engine = QueryEngine()

cards = [
    AgentCard(did="did:key:z1", name="expensive", capabilities=["summarize"],
              cost=CostInfo(per_task=10.0), latency_p99_ms=100, endpoint="http://a"),
    AgentCard(did="did:key:z2", name="cheap-slow", capabilities=["summarize"],
              cost=CostInfo(per_task=1.0), latency_p99_ms=5000, endpoint="http://b"),
    AgentCard(did="did:key:z3", name="cheap-fast", capabilities=["summarize"],
              cost=CostInfo(per_task=1.0), latency_p99_ms=200, endpoint="http://c"),
    AgentCard(did="did:key:z4", name="other", capabilities=["translate"],
              cost=CostInfo(per_task=0.5), endpoint="http://d"),
]

# No filters — returns all with "summarize", cheapest first then by latency
results = engine.query(cards, capability="summarize")
print([c.name for c in results])
# ['cheap-fast', 'cheap-slow', 'expensive']

# Cost filter
results = engine.query(cards, capability="summarize", max_cost_per_task=2.0)
print([c.name for c in results])
# ['cheap-fast', 'cheap-slow']

# Cost + latency filter
results = engine.query(cards, capability="summarize", max_cost_per_task=2.0, max_latency_ms=1000)
print([c.name for c in results])
# ['cheap-fast']
```

---

## Rate limiting

The registry uses `slowapi` (a Starlette/FastAPI port of Flask-Limiter) backed by in-memory storage.

| Endpoint | Limit |
|----------|-------|
| `POST /v1/agents` | 10 per minute per IP |
| `GET /v1/agents/query` | 60 per minute per IP |
| `GET /v1/agents/{did}` | 60 per minute per IP |

When a limit is exceeded, the response is `429 Too Many Requests` with a `Retry-After` header.

To change limits, modify the `PUBLISH_RATE` and `QUERY_RATE` constants in `agentpassport_registry.routes`.

---

## RegistryClient (Python SDK)

**Module:** `agentpassport.registry_client`

```python
class RegistryClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None
    async def publish(self, card: AgentCard) -> dict
    async def get(self, did: str) -> AgentCard | None
    async def search(
        self,
        capability: str | None = None,
        max_cost: float | None = None,
        max_latency_ms: int | None = None,
    ) -> list[AgentCard]
```

Client for the registry service, used from the agent SDK.

### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | required | Registry service base URL |
| `timeout` | `float` | `10.0` | HTTP request timeout in seconds |

### `RegistryClient.publish()`

Publish an `AgentCard` to the registry.

**Returns:** `dict` — `{"status": "registered", "did": "..."}` on success.

**Raises:** `httpx.HTTPStatusError` on non-2xx.

### `RegistryClient.get()`

Look up an agent by DID.

**Returns:** `AgentCard | None` — `None` if not found (404).

### `RegistryClient.search()`

Query agents by capability and optional constraints.

**Returns:** `list[AgentCard]` — matching agents, sorted by cost then latency.

**Example:**
```python
from agentpassport import Agent, AgentCard, CostInfo, sign_agent_card, RegistryClient, generate_keypair

agent_priv, agent_pub = generate_keypair()
agent = Agent(name="my-agent", private_key=agent_priv)
client = RegistryClient("http://registry:8000")

# Build and publish a signed card
card = AgentCard(
    did=agent.did,
    name=agent.name,
    capabilities=["summarize"],
    cost=CostInfo(per_task=2.0),
    latency_p99_ms=800,
    endpoint="http://my-agent:8080",
)
signed = sign_agent_card(card, agent_priv)
result = await client.publish(signed)
print(result)  # {'status': 'registered', 'did': 'did:key:z6Mk...'}

# Discover agents for delegation
candidates = await client.search(
    capability="summarize",
    max_cost=5.0,
    max_latency_ms=2000,
)
if candidates:
    best = candidates[0]  # cheapest and fastest
    print(f"Best agent: {best.name} at {best.endpoint}")
```

---

## Full integration example

A complete example showing registry-driven agent discovery and delegation.

```python
# registry_integration.py

import asyncio
from agentpassport import (
    Agent, AgentCard, CostInfo,
    sign_agent_card, verify_agent_card, parse_did,
    RegistryClient, TaskEnvelope, Intent, Constraints,
    generate_keypair,
)

REGISTRY_URL = "http://localhost:8000"

# ── Publisher agent (runs at startup) ─────────────────────────────────────────

async def publish_agents():
    client = RegistryClient(REGISTRY_URL)
    agents_config = [
        ("fast-summarizer",  ["summarize"],        1.0, 500,  "http://fast:8080"),
        ("good-summarizer",  ["summarize"],        2.5, 1500, "http://good:8081"),
        ("multi-tool-agent", ["summarize", "search"], 3.0, 1000, "http://multi:8082"),
    ]

    for name, caps, cost, latency, endpoint in agents_config:
        agent_priv, agent_pub = generate_keypair()
        agent = Agent(name=name, private_key=agent_priv)
        card = AgentCard(
            did=agent.did, name=name, capabilities=caps,
            cost=CostInfo(per_task=cost), latency_p99_ms=latency, endpoint=endpoint,
        )
        signed = sign_agent_card(card, agent_priv)
        await client.publish(signed)
        print(f"Published: {name} (cost={cost}, latency={latency}ms)")


# ── Orchestrator that discovers and delegates ──────────────────────────────────

async def orchestrate():
    client = RegistryClient(REGISTRY_URL)

    # Find the best summarizer (cheapest, under 1 second latency)
    candidates = await client.search(
        capability="summarize",
        max_cost=3.0,
        max_latency_ms=1000,
    )
    print(f"Found {len(candidates)} candidate(s)")
    for c in candidates:
        print(f"  {c.name}: cost={c.cost.per_task if c.cost else '?'}, latency={c.latency_p99_ms}ms")

    if not candidates:
        print("No suitable agent found!")
        return

    best = candidates[0]
    print(f"Selected: {best.name} at {best.endpoint}")

    # Verify the card's signature before trusting it
    pub_key = parse_did(best.did)
    if not verify_agent_card(best, pub_key):
        print("WARNING: Card signature invalid!")
        return

    print("Card signature verified.")

    # Create orchestrator identity and delegate
    orchestrator = Agent(name="orchestrator")
    result = await orchestrator.delegate(
        task=TaskEnvelope(
            intent=Intent(type="summarize", params={"text": "Hello, world!"}),
            constraints=Constraints(budget_credits=10.0, max_delegations=1),
        ),
        target_did=best.did,
        endpoint=best.endpoint,
        scope=["invoke:llm"],
    )
    print(f"Result: {result}")


async def main():
    print("=== Publishing agents ===")
    await publish_agents()

    print("\n=== Orchestrating via registry ===")
    await orchestrate()


asyncio.run(main())
```
