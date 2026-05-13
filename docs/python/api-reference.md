# AgentPassport Python SDK — API Reference

Complete reference for every exported symbol from the `agentpassport` package. For conceptual background see `docs/concepts.md`.

---

## Table of Contents

- [Installation](#installation)
- [Module: `agentpassport`](#module-agentpassport)
- [Class: `Agent`](#class-agent)
- [Identity functions](#identity-functions)
  - [`generate_keypair()`](#generate_keypair)
  - [`did_from_public_key()`](#did_from_public_key)
  - [`parse_did()`](#parse_did)
  - [`sign_delegation()`](#sign_delegation)
  - [`verify_auth_chain()`](#verify_auth_chain)
  - [`sign_agent_card()`](#sign_agent_card)
  - [`verify_agent_card()`](#verify_agent_card)
- [Class: `AgentCard`](#class-agentcard)
- [Class: `CostInfo`](#class-costinfo)
- [Class: `TaskEnvelope`](#class-taskenvelope)
- [Class: `Intent`](#class-intent)
- [Class: `Constraints`](#class-constraints)
- [Enum: `TaskState`](#enum-taskstate)
- [Class: `ObservabilityEvent`](#class-observabilityevent)
- [Class: `EventEmitter`](#class-eventemitter)
- [Class: `StdoutSink`](#class-stdoutsink)
- [Class: `FileSink`](#class-filesink)
- [Class: `MemorySink`](#class-memorysink)
- [Class: `OtelSink`](#class-otelsink)
- [Class: `TrustMiddleware`](#class-trustmiddleware)
- [Exception: `ScopeError`](#exception-scopeerror)
- [Class: `TaskLifecycle`](#class-tasklifecycle)
- [Exception: `InvalidTransitionError`](#exception-invalidtransitionerror)
- [Class: `BudgetTracker`](#class-budgettracker)
- [Exception: `BudgetExceededError`](#exception-budgetexceedederror)
- [Function: `create_subtask()`](#function-create_subtask)
- [Class: `RevocationRegistry`](#class-revocationregistry)
- [Class: `InMemoryRevocationRegistry`](#class-inmemoryrevocationregistry)
- [Class: `SqliteRevocationRegistry`](#class-sqliterevocationregistry)
- [Class: `RegistryClient`](#class-registryclient)
- [Class: `HttpTransport`](#class-httptransport)
- [Class: `StdioTransport`](#class-stdiotransport)
- [Internal helpers (identity)](#internal-helpers-identity)

---

## Installation

```bash
pip install agentpassport

# With OpenTelemetry support:
pip install agentpassport[otel]
```

Python 3.11+ required. Key dependencies: `pydantic`, `PyNaCl`, `httpx`.

---

## Module: `agentpassport`

The top-level `agentpassport` module re-exports everything you need for typical usage. You rarely need to import from sub-modules directly.

```python
from agentpassport import (
    # Agent
    Agent,
    # Identity
    did_from_public_key,
    generate_keypair,
    parse_did,
    sign_agent_card,
    sign_delegation,
    verify_agent_card,
    verify_auth_chain,
    # Observability
    EventEmitter,
    FileSink,
    MemorySink,
    OtelSink,
    StdoutSink,
    # Registry
    RegistryClient,
    # Revocation
    InMemoryRevocationRegistry,
    RevocationRegistry,
    SqliteRevocationRegistry,
    # Task
    BudgetExceededError,
    BudgetTracker,
    TaskLifecycle,
    create_subtask,
    # Transport
    HttpTransport,
    StdioTransport,
    # Trust
    ScopeError,
    TrustMiddleware,
    # Types
    AgentCard,
    Constraints,
    CostInfo,
    Intent,
    ObservabilityEvent,
    TaskEnvelope,
    TaskState,
)
```

---

## Class: `Agent`

**Module:** `agentpassport.agent`

The central class. Owns a keypair, a DID, capability handlers, trusted keys, and an event emitter. Wires together trust middleware, task lifecycle, and observability automatically.

### Constructor

```python
Agent(
    name: str,
    private_key: bytes | None = None,
    emitter: EventEmitter | None = None,
) -> Agent
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | Yes | — | Human-readable name for this agent. Used in logs and can be published in an `AgentCard`. |
| `private_key` | `bytes \| None` | No | `None` | 64-byte Ed25519 keypair bytes (first 32: seed, last 32: public key). If `None`, a fresh keypair is generated automatically. |
| `emitter` | `EventEmitter \| None` | No | `None` | Observability emitter. If `None`, defaults to an `EventEmitter` with a single `StdoutSink`. |

**Raises:** Nothing on construction. If `private_key` is provided but malformed (wrong length, not valid Ed25519), PyNaCl will raise `nacl.exceptions.ValueError` when the key is used.

**Attributes set on construction:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Agent name |
| `did` | `str` | `did:key:z...` derived from the public key |
| `emitter` | `EventEmitter` | Event emitter |
| `capabilities` | `dict[str, CapabilityHandler]` | Registered capability handlers |

**Example 1: Auto-generate keypair**
```python
from agentpassport import Agent

agent = Agent(name="summarizer")
print(agent.did)
# did:key:z6Mk...
```

**Example 2: Restore from persisted private key**
```python
import json
from agentpassport import Agent

# Load key persisted from a previous run
with open("agent_key.bin", "rb") as f:
    private_key = f.read()

agent = Agent(name="summarizer", private_key=private_key)
# agent.did will be the same as the previous run
```

**Example 3: Custom emitter (file logging)**
```python
from pathlib import Path
from agentpassport import Agent, EventEmitter, FileSink

emitter = EventEmitter(sinks=[FileSink(Path("agent.ndjson"))])
agent = Agent(name="summarizer", emitter=emitter)
```

---

### `Agent.capability()`

```python
agent.capability(
    name: str,
    requires: list[str] | None = None,
) -> Callable[[CapabilityHandler], CapabilityHandler]
```

Decorator that registers an async function as the handler for a named capability.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | Yes | — | The capability name. Must match `task.intent.type` for the handler to be dispatched. |
| `requires` | `list[str] \| None` | No | `None` | List of scope strings the incoming task's auth chain must grant. If `None` or `[]`, no scope check is performed. |

**Returns:** A decorator that, when applied to an async function `f(task: TaskEnvelope) -> dict`, registers `f` and returns it unchanged.

**The handler signature:**
```python
async def handler(task: TaskEnvelope) -> dict[str, Any]:
    ...
```

**Raises (at decoration time):** Nothing.

**Raises (at call time via `handle()`):**
- `ScopeError` — if `requires` is set and the auth chain doesn't cover all required scopes.
- Any exception raised by the handler propagates out of `handle()`.

**Example 1: Simple capability, no scope required**
```python
from agentpassport import Agent, TaskEnvelope

agent = Agent(name="echo")

@agent.capability("echo")
async def echo(task: TaskEnvelope) -> dict:
    return {"echoed": task.intent.params.get("message", "")}
```

**Example 2: Scoped capability**
```python
@agent.capability("read_customers", requires=["read:db:customers"])
async def read_customers(task: TaskEnvelope) -> dict:
    # Only runs if the auth chain grants read:db:customers (or *)
    rows = await db.query("SELECT * FROM customers LIMIT 100")
    return {"rows": rows}
```

**Example 3: Multiple required scopes**
```python
@agent.capability(
    "generate_report",
    requires=["read:db:orders", "read:db:customers", "write:storage:reports"]
)
async def generate_report(task: TaskEnvelope) -> dict:
    ...
    return {"report_id": "r_123"}
```

---

### `Agent.trust_keys()`

```python
agent.trust_keys(keys: dict[str, bytes]) -> None
```

Register known public keys for auth chain verification. Keys must be registered before tasks are handled; tokens signed by unknown issuers are silently rejected by `verify_auth_chain`.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `keys` | `dict[str, bytes]` | Yes | Mapping from issuer DID string to 32-byte Ed25519 public key bytes. |

**Returns:** `None`

**Raises:** Nothing.

**Notes:**
- Calling `trust_keys` multiple times is safe — new entries are merged into the existing map.
- The agent's own key is not automatically trusted; if the agent can receive tasks delegated by itself, add its own key: `agent.trust_keys({agent.did: agent.public_key})`.

**Example 1: Trust an orchestrator**
```python
from agentpassport import Agent, generate_keypair, did_from_public_key

orchestrator_priv, orchestrator_pub = generate_keypair()
orchestrator_did = did_from_public_key(orchestrator_pub)

agent = Agent(name="worker")
agent.trust_keys({orchestrator_did: orchestrator_pub})
```

**Example 2: Trust multiple issuers**
```python
agent.trust_keys({
    orchestrator_did: orchestrator_pub,
    supervisor_did: supervisor_pub,
    peer_agent_did: peer_pub,
})
```

**Example 3: Trust keys from a registry response**
```python
cards = await registry.search(capability="read_data")
trusted = {card.did: parse_did(card.did) for card in cards}
agent.trust_keys(trusted)
```

---

### `Agent.delegate()`

```python
async def agent.delegate(
    task: TaskEnvelope,
    target_did: str,
    endpoint: str,
    scope: list[str] | None = None,
    ttl_seconds: int = 3600,
) -> dict
```

Sign a new delegation JWT and send the task to `target_did` at `endpoint`. Returns the target's response as a dict.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task` | `TaskEnvelope` | Yes | — | The task to delegate. The original task is not mutated; a copy with the extended auth chain is sent. |
| `target_did` | `str` | Yes | — | The DID of the target agent (becomes the `sub` claim in the new JWT). |
| `endpoint` | `str` | Yes | — | URL of the target agent's HTTP endpoint. |
| `scope` | `list[str] \| None` | No | `None` (→ `["*"]`) | Scopes to grant in the new delegation token. If `None`, grants wildcard. |
| `ttl_seconds` | `int` | No | `3600` | Validity window of the new JWT in seconds. |

**Returns:** `dict` — the JSON-decoded response body from the target agent.

**Raises:**
- `httpx.HTTPStatusError` — if the target returns a non-2xx status.
- `httpx.RequestError` — if the network request fails.
- Any exception from the underlying `HttpTransport.send()`.

**Example 1: Delegate with wildcard scope**
```python
result = await orchestrator.delegate(
    task=task,
    target_did=worker_agent.did,
    endpoint="http://worker:8080",
)
```

**Example 2: Delegate with narrowed scope**
```python
result = await orchestrator.delegate(
    task=task,
    target_did=db_agent.did,
    endpoint="http://db-agent:8080",
    scope=["read:db:customers"],
    ttl_seconds=600,  # 10 minutes
)
```

**Example 3: Error handling**
```python
import httpx

try:
    result = await orchestrator.delegate(task, target_did, endpoint)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 403:
        print("Target rejected the auth chain")
    else:
        raise
```

---

### `Agent.handle()`

```python
async def agent.handle(task: TaskEnvelope) -> dict[str, Any]
```

Handle an incoming task by dispatching to the registered capability handler. Runs scope check, lifecycle transitions, and emits observability events automatically.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | `TaskEnvelope` | Yes | The incoming task to handle. |

**Returns:** `dict[str, Any]` — the dict returned by the capability handler.

**Raises:**
- `ValueError` — if no handler is registered for `task.intent.type`.
- `ScopeError` — if the capability declares `requires=[...]` and the auth chain doesn't cover it.
- Any exception raised by the handler (handler exceptions cause the task to transition to `FAILED` and emit a `task_failed` event before re-raising).

**Side effects:**
- Transitions `task.state` through `DELEGATED → ACCEPTED → RUNNING → COMPLETED` (or `FAILED`).
- Emits events: `task_accepted`, `task_running`, `task_completed` (or `task_failed`).

**Example 1: Basic usage (HTTP server wrapping)**
```python
from fastapi import FastAPI, Request, HTTPException
from agentpassport import Agent, TaskEnvelope, ScopeError

app = FastAPI()
agent = Agent(name="worker")

@agent.capability("process")
async def process(task):
    return {"status": "done"}

@app.post("/agentpassport/tasks")
async def receive_task(request: Request):
    body = await request.body()
    task = TaskEnvelope.model_validate_json(body)
    try:
        result = await agent.handle(task)
        return result
    except ScopeError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Example 2: Handling a ScopeError separately from handler errors**
```python
try:
    result = await agent.handle(task)
except ScopeError as e:
    # Auth chain didn't grant the required scope
    logger.warning(f"Scope denied: {e}")
    return {"error": "forbidden", "detail": str(e)}
except Exception as e:
    # Handler raised an error — task is now in FAILED state
    logger.error(f"Task failed: {e}")
    return {"error": "internal", "detail": str(e)}
```

**Example 3: Unknown capability**
```python
task.intent.type = "nonexistent"
try:
    await agent.handle(task)
except ValueError as e:
    print(e)  # "No handler for capability: nonexistent"
```

---

## Identity functions

### `generate_keypair()`

**Module:** `agentpassport.identity.did`

```python
def generate_keypair() -> tuple[bytes, bytes]
```

Generate a new Ed25519 keypair.

**Parameters:** None

**Returns:** `tuple[bytes, bytes]` — `(private_key, public_key)` where:
- `private_key`: 64 bytes. First 32 bytes are the Ed25519 seed. Last 32 bytes are the public key.
- `public_key`: 32 bytes. The Ed25519 verify key.

**Raises:** Nothing. Uses PyNaCl's `SigningKey.generate()` which uses OS-provided randomness.

**Thread safety:** Safe to call from multiple threads simultaneously.

**Example 1: Basic keypair generation**
```python
from agentpassport import generate_keypair

private_key, public_key = generate_keypair()
print(len(private_key))  # 64
print(len(public_key))   # 32
```

**Example 2: Persist and restore**
```python
import os

private_key, public_key = generate_keypair()

# Persist
with open("agent.key", "wb") as f:
    f.write(private_key)

# Restore
with open("agent.key", "rb") as f:
    restored_private = f.read()

restored_public = restored_private[32:]  # last 32 bytes are the public key
```

**Example 3: Use with Agent**
```python
from agentpassport import Agent, generate_keypair

priv, pub = generate_keypair()
agent = Agent(name="my-agent", private_key=priv)
print(agent.did)  # deterministic from pub key
```

---

### `did_from_public_key()`

**Module:** `agentpassport.identity.did`

```python
def did_from_public_key(public_key: bytes) -> str
```

Create a `did:key:z...` DID from raw Ed25519 public key bytes.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `public_key` | `bytes` | Yes | 32-byte Ed25519 public key. |

**Returns:** `str` — the DID string, e.g. `"did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"`.

**Raises:** Nothing explicitly, but passing non-32-byte input will produce a technically valid but incorrect DID (the encoding will succeed with wrong data).

**Algorithm:**
1. Prepend multicodec prefix `[0xED, 0x01]` to the 32-byte key.
2. Base58btc-encode the 34-byte result.
3. Prepend `"z"` (multibase prefix for base58btc).
4. Return `f"did:key:z{encoded}"`.

**Example 1: Basic usage**
```python
from agentpassport import generate_keypair, did_from_public_key

_, pub = generate_keypair()
did = did_from_public_key(pub)
print(did)  # did:key:z6Mk...
```

**Example 2: Determinism — same key always gives same DID**
```python
from agentpassport import generate_keypair, did_from_public_key

_, pub = generate_keypair()
assert did_from_public_key(pub) == did_from_public_key(pub)
```

**Example 3: Round-trip through parse_did**
```python
from agentpassport import generate_keypair, did_from_public_key, parse_did

_, pub = generate_keypair()
did = did_from_public_key(pub)
recovered = parse_did(did)
assert recovered == pub  # True
```

---

### `parse_did()`

**Module:** `agentpassport.identity.did`

```python
def parse_did(did: str) -> bytes
```

Extract the raw Ed25519 public key bytes from a `did:key:` string.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `did` | `str` | Yes | A `did:key:z...` DID string. |

**Returns:** `bytes` — 32-byte Ed25519 public key.

**Raises:**
- `ValueError` — if `did` does not start with `"did:key:z"`.
- `ValueError` — if the decoded bytes don't begin with the Ed25519 multicodec prefix `0xED 0x01`.

**Example 1: Extract public key from DID**
```python
from agentpassport import parse_did

did = "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
pub_key = parse_did(did)
print(len(pub_key))  # 32
```

**Example 2: Error on invalid DID**
```python
from agentpassport import parse_did

try:
    parse_did("did:web:example.com")
except ValueError as e:
    print(e)  # Invalid did:key DID (expected did:key:z...): did:web:example.com
```

**Example 3: Use in trust_keys**
```python
from agentpassport import Agent, parse_did

agent = Agent(name="worker")
issuer_did = "did:key:z6Mk..."

# Derive the public key from the DID itself (no separate channel needed)
issuer_pub = parse_did(issuer_did)
agent.trust_keys({issuer_did: issuer_pub})
```

---

### `sign_delegation()`

**Module:** `agentpassport.identity.signing`

```python
def sign_delegation(
    issuer_private_key: bytes,
    issuer_did: str,
    subject_did: str,
    scope: list[str],
    ttl_seconds: int = 3600,
    max_delegations: int = 0,
) -> str
```

Create a signed delegation JWT for one hop in the trust chain. Returns a compact `header.payload.signature` JWT string.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `issuer_private_key` | `bytes` | Yes | — | 64-byte keypair bytes. Only the first 32 bytes (the seed) are used for signing. |
| `issuer_did` | `str` | Yes | — | The issuer's DID. Becomes the `iss` claim. |
| `subject_did` | `str` | Yes | — | The subject's DID (who is being authorized). Becomes the `sub` claim. |
| `scope` | `list[str]` | Yes | — | List of permission strings granted to the subject. |
| `ttl_seconds` | `int` | No | `3600` | Token validity in seconds from now. |
| `max_delegations` | `int` | No | `0` | How many further hops the subject may delegate. `0` means the subject cannot delegate further. |

**Returns:** `str` — compact JWT string (`header.payload.sig`, all base64url-encoded, no padding).

**Raises:** Nothing explicitly (PyNaCl signing is deterministic and always succeeds for valid inputs).

**Claims produced:**
```json
{
  "iss": "<issuer_did>",
  "sub": "<subject_did>",
  "iat": <unix_seconds_now>,
  "exp": <unix_seconds_now + ttl_seconds>,
  "jti": "<uuid4>",
  "scope": ["..."],
  "max_delegations": <int>
}
```

**Example 1: Basic delegation**
```python
from agentpassport import generate_keypair, did_from_public_key, sign_delegation

issuer_priv, issuer_pub = generate_keypair()
_, subject_pub = generate_keypair()

issuer_did = did_from_public_key(issuer_pub)
subject_did = did_from_public_key(subject_pub)

token = sign_delegation(
    issuer_private_key=issuer_priv,
    issuer_did=issuer_did,
    subject_did=subject_did,
    scope=["read:db:customers"],
    ttl_seconds=3600,
)
print(token)  # eyJ...
```

**Example 2: Short-lived token with wildcard scope**
```python
token = sign_delegation(
    issuer_private_key=issuer_priv,
    issuer_did=issuer_did,
    subject_did=subject_did,
    scope=["*"],
    ttl_seconds=300,  # 5 minutes
)
```

**Example 3: Allow further delegation**
```python
# Subject can re-delegate up to 2 more hops
token = sign_delegation(
    issuer_private_key=issuer_priv,
    issuer_did=issuer_did,
    subject_did=subject_did,
    scope=["read:db"],
    ttl_seconds=3600,
    max_delegations=2,
)
```

---

### `verify_auth_chain()`

**Module:** `agentpassport.identity.signing`

```python
def verify_auth_chain(
    auth_chain: list[str],
    expected_subject: str,
    known_public_keys: dict[str, bytes],
    revocation_registry: RevocationRegistry | None = None,
) -> bool
```

Verify a complete chain of delegation JWTs. Returns `True` only if every check passes for every hop.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `auth_chain` | `list[str]` | Yes | — | Ordered list of compact JWT strings, one per delegation hop. |
| `expected_subject` | `str` | Yes | — | The DID that the last token must name as `sub`. Usually the receiving agent's DID. |
| `known_public_keys` | `dict[str, bytes]` | Yes | — | Map from issuer DID to 32-byte public key. Tokens from unknown issuers are rejected. |
| `revocation_registry` | `RevocationRegistry \| None` | No | `None` | If provided, each token's `jti` is checked for revocation. |

**Returns:** `bool` — `True` if the entire chain is valid, `False` otherwise. Never raises; all errors are caught and return `False`.

**Verification steps per token:**
1. Structural validity (3 parts)
2. `alg: EdDSA` in header
3. Issuer in `known_public_keys`
4. Valid Ed25519 signature
5. `iat <= now <= exp` (temporal validity)
6. `jti` is non-empty
7. `jti` not revoked (if registry provided)

**Final check:** Last token's `sub == expected_subject`.

**Example 1: Verify a single-hop chain**
```python
from agentpassport import (
    generate_keypair, did_from_public_key,
    sign_delegation, verify_auth_chain,
)

issuer_priv, issuer_pub = generate_keypair()
_, subject_pub = generate_keypair()
issuer_did = did_from_public_key(issuer_pub)
subject_did = did_from_public_key(subject_pub)

token = sign_delegation(issuer_priv, issuer_did, subject_did, ["read:db"])

ok = verify_auth_chain(
    auth_chain=[token],
    expected_subject=subject_did,
    known_public_keys={issuer_did: issuer_pub},
)
assert ok is True
```

**Example 2: Multi-hop chain**
```python
a_priv, a_pub = generate_keypair()
b_priv, b_pub = generate_keypair()
_, c_pub = generate_keypair()

a_did = did_from_public_key(a_pub)
b_did = did_from_public_key(b_pub)
c_did = did_from_public_key(c_pub)

jwt_ab = sign_delegation(a_priv, a_did, b_did, ["*"])
jwt_bc = sign_delegation(b_priv, b_did, c_did, ["read:db"])

ok = verify_auth_chain(
    auth_chain=[jwt_ab, jwt_bc],
    expected_subject=c_did,
    known_public_keys={a_did: a_pub, b_did: b_pub},
)
assert ok is True
```

**Example 3: With revocation registry**
```python
from agentpassport import InMemoryRevocationRegistry
import json, base64

registry = InMemoryRevocationRegistry()

token = sign_delegation(issuer_priv, issuer_did, subject_did, ["*"])

# Extract JTI to revoke
payload = token.split(".")[1]
padding = 4 - len(payload) % 4
claims = json.loads(base64.urlsafe_b64decode(payload + "=" * padding))
jti = claims["jti"]

registry.revoke(jti)

ok = verify_auth_chain(
    auth_chain=[token],
    expected_subject=subject_did,
    known_public_keys={issuer_did: issuer_pub},
    revocation_registry=registry,
)
assert ok is False
```

---

### `sign_agent_card()`

**Module:** `agentpassport.identity.signing`

```python
def sign_agent_card(card: AgentCard, private_key_seed: bytes) -> AgentCard
```

Return a new `AgentCard` with the `signature` field populated.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `card` | `AgentCard` | Yes | The agent card to sign. Must have `did`, `name`, `capabilities`, and `endpoint` populated. |
| `private_key_seed` | `bytes` | Yes | 64-byte keypair or 32-byte seed. Only the first 32 bytes are used. |

**Returns:** `AgentCard` — a new `AgentCard` instance with `signature` set to the hex-encoded Ed25519 signature over `card.canonical_payload()`.

**Raises:** Nothing explicitly.

**What is signed:** `SHA-256(JSON({capabilities:sorted, did, endpoint, name}))`. See [`AgentCard.canonical_payload()`](#class-agentcard).

**Example 1: Sign and publish a card**
```python
from agentpassport import (
    Agent, AgentCard, CostInfo, sign_agent_card, generate_keypair, did_from_public_key,
)

priv, pub = generate_keypair()
did = did_from_public_key(pub)

card = AgentCard(
    did=did,
    name="summarizer",
    capabilities=["summarize", "extract_keywords"],
    endpoint="http://summarizer.internal:8080",
    cost=CostInfo(per_task=0.5),
)

signed_card = sign_agent_card(card, priv)
print(signed_card.signature)  # hex string
```

**Example 2: Immutability — original card unchanged**
```python
card = AgentCard(did=did, name="x", capabilities=["a"], endpoint="http://x")
signed = sign_agent_card(card, priv)
assert card.signature is None          # original unchanged
assert signed.signature is not None    # copy has signature
```

---

### `verify_agent_card()`

**Module:** `agentpassport.identity.signing`

```python
def verify_agent_card(card: AgentCard, public_key_bytes: bytes) -> bool
```

Verify the `AgentCard`'s `signature` field against its canonical payload.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `card` | `AgentCard` | Yes | The agent card to verify. |
| `public_key_bytes` | `bytes` | Yes | 32-byte Ed25519 public key of the expected signer. |

**Returns:** `bool` — `True` if the signature is present and valid, `False` otherwise (no signature, bad hex, or invalid signature).

**Raises:** Nothing.

**Example 1: Verify a card from the registry**
```python
from agentpassport import verify_agent_card, parse_did

card = await registry.get(agent_did)
pub_key = parse_did(card.did)  # public key is embedded in the DID itself

if verify_agent_card(card, pub_key):
    print("Card is authentic")
else:
    print("Card signature invalid — may be tampered")
```

**Example 2: Tampered card rejected**
```python
signed_card = sign_agent_card(card, priv)

# Tamper with the endpoint
tampered = signed_card.model_copy(update={"endpoint": "http://evil.com"})

ok = verify_agent_card(tampered, pub)
assert ok is False  # signature covers endpoint
```

---

## Class: `AgentCard`

**Module:** `agentpassport.types.agent_card`

Pydantic model. Shareable, signed description of an agent.

```python
class AgentCard(BaseModel):
    did: str
    name: str
    version: str = "0.1.0"
    capabilities: list[str]
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    cost: CostInfo = CostInfo()
    latency_p99_ms: int | None = None
    trust_requirements: list[str] = []
    transports: list[str] = ["http"]
    endpoint: str
    signature: str | None = None
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `did` | `str` | required | Agent's DID |
| `name` | `str` | required | Human-readable name |
| `version` | `str` | `"0.1.0"` | SemVer version string |
| `capabilities` | `list[str]` | required | Names of capabilities the agent handles |
| `input_schema` | `dict` | `{}` | JSON Schema for task input params |
| `output_schema` | `dict` | `{}` | JSON Schema for task output |
| `cost` | `CostInfo` | default | Pricing info |
| `latency_p99_ms` | `int \| None` | `None` | P99 latency hint in milliseconds |
| `trust_requirements` | `list[str]` | `[]` | Scope strings callers must hold |
| `transports` | `list[str]` | `["http"]` | Supported transports |
| `endpoint` | `str` | required | Base URL where the agent receives tasks |
| `signature` | `str \| None` | `None` | Hex-encoded Ed25519 signature over canonical payload |

### `AgentCard.canonical_payload()`

```python
def canonical_payload(self) -> bytes
```

Returns the bytes that are signed/verified. This is `SHA-256(compact_json)` where `compact_json` is the JSON encoding of `{capabilities: sorted(self.capabilities), did, endpoint, name}` with sorted keys and no extra whitespace.

**Returns:** `bytes` — 32-byte SHA-256 digest.

---

## Class: `CostInfo`

**Module:** `agentpassport.types.agent_card`

```python
class CostInfo(BaseModel):
    currency: str = "credits"
    per_task: float = 0.0
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `currency` | `str` | `"credits"` | Currency unit (free-form string) |
| `per_task` | `float` | `0.0` | Cost per task invocation |

---

## Class: `TaskEnvelope`

**Module:** `agentpassport.types.task`

```python
class TaskEnvelope(BaseModel):
    version: str = "1.0"
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:16]}")
    parent_id: str | None = None
    intent: Intent
    constraints: Constraints = Field(default_factory=Constraints)
    auth_chain: list[str] = Field(default_factory=list)
    result_schema: dict[str, Any] | None = None
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:16]}")
    transport: str = "http"
    state: TaskState = TaskState.CREATED
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | `str` | `"1.0"` | Protocol version |
| `id` | `str` | `task_<16 hex chars>` | Unique task ID |
| `parent_id` | `str \| None` | `None` | Parent task ID for subtask trees |
| `intent` | `Intent` | required | What to do |
| `constraints` | `Constraints` | default | Budget and delegation limits |
| `auth_chain` | `list[str]` | `[]` | Delegation JWT chain |
| `result_schema` | `dict \| None` | `None` | Expected output schema |
| `trace_id` | `str` | `trace_<16 hex chars>` | Distributed trace ID |
| `transport` | `str` | `"http"` | Transport hint |
| `state` | `TaskState` | `CREATED` | Lifecycle state |

---

## Class: `Intent`

**Module:** `agentpassport.types.task`

```python
class Intent(BaseModel):
    type: str
    params: dict[str, Any] = {}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | required | Capability name to invoke (matched against registered handlers) |
| `params` | `dict` | `{}` | Parameters passed to the handler |

---

## Class: `Constraints`

**Module:** `agentpassport.types.task`

```python
class Constraints(BaseModel):
    budget_credits: float = 100.0
    deadline_ms: int | None = None
    max_delegations: int = 10
    allowed_capabilities: list[str] = []
    denied_capabilities: list[str] = []
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `budget_credits` | `float` | `100.0` | Total credit budget. Must be >= 0 (validated). |
| `deadline_ms` | `int \| None` | `None` | Deadline in milliseconds since epoch |
| `max_delegations` | `int` | `10` | Remaining delegation depth |
| `allowed_capabilities` | `list[str]` | `[]` | Whitelist (empty = allow all) |
| `denied_capabilities` | `list[str]` | `[]` | Blacklist |

**Validation:** `budget_credits` raises `ValueError` if negative.

---

## Enum: `TaskState`

**Module:** `agentpassport.types.task`

```python
class TaskState(str, Enum):
    CREATED   = "created"
    DELEGATED = "delegated"
    ACCEPTED  = "accepted"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
```

Inherits from both `str` and `Enum`, so `TaskState.CREATED == "created"` is `True`. Safe to serialize directly to JSON.

---

## Class: `ObservabilityEvent`

**Module:** `agentpassport.types.events`

Pydantic model emitted by `EventEmitter` and written to sinks.

```python
class ObservabilityEvent(BaseModel):
    trace_id: str
    task_id: str
    event: str
    from_state: str | None = None
    to_state: str | None = None
    agent: str
    timestamp: str    # ISO 8601 UTC, auto-set
    cost_used: float = 0.0
    budget_remaining: float = 0.0
    metadata: dict[str, Any] = {}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `trace_id` | `str` | required | Distributed trace identifier |
| `task_id` | `str` | required | Task that produced this event |
| `event` | `str` | required | Event name (e.g. `"task_accepted"`) |
| `from_state` | `str \| None` | `None` | Previous state (state change events) |
| `to_state` | `str \| None` | `None` | New state (state change events) |
| `agent` | `str` | required | DID of the emitting agent |
| `timestamp` | `str` | auto | ISO 8601 UTC timestamp at creation time |
| `cost_used` | `float` | `0.0` | Credits spent |
| `budget_remaining` | `float` | `0.0` | Credits remaining |
| `metadata` | `dict` | `{}` | Arbitrary extra key-value data |

---

## Class: `EventEmitter`

**Module:** `agentpassport.observability.emitter`

```python
class EventEmitter:
    def __init__(self, sinks: list[Sink] | None = None) -> None
```

Fan-out event bus. Events are written synchronously to all registered sinks.

### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sinks` | `list[Sink] \| None` | `None` (→ `[]`) | Initial list of sinks. Can be added to later with `add_sink()`. |

### `EventEmitter.add_sink()`

```python
def add_sink(self, sink: Sink) -> None
```

Append a sink. Events emitted after this call will be written to the new sink.

### `EventEmitter.emit()`

```python
def emit(
    self,
    trace_id: str,
    task_id: str,
    event: str,
    agent: str,
    **kwargs: object,
) -> None
```

Create an `ObservabilityEvent` and write it to all sinks.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `trace_id` | `str` | Yes | Distributed trace ID |
| `task_id` | `str` | Yes | Task ID |
| `event` | `str` | Yes | Event name |
| `agent` | `str` | Yes | Emitting agent's DID |
| `**kwargs` | any | No | Additional fields passed to `ObservabilityEvent` (e.g. `metadata={"error": "..."}`) |

### `EventEmitter.emit_state_change()`

```python
def emit_state_change(
    self,
    trace_id: str,
    task_id: str,
    agent: str,
    from_state: str,
    to_state: str,
    cost_used: float = 0.0,
    budget_remaining: float = 0.0,
) -> None
```

Convenience wrapper for `emit(event="state_change", ...)`.

**Example 1: Multiple sinks**
```python
from pathlib import Path
from agentpassport import EventEmitter, StdoutSink, FileSink, MemorySink

emitter = EventEmitter(sinks=[StdoutSink()])
emitter.add_sink(FileSink(Path("events.ndjson")))
test_sink = MemorySink()
emitter.add_sink(test_sink)

emitter.emit(
    trace_id="trace_abc",
    task_id="task_xyz",
    event="custom_event",
    agent="did:key:z6Mk...",
    metadata={"key": "value"},
)

print(len(test_sink.events))  # 1
```

**Example 2: State change event**
```python
emitter.emit_state_change(
    trace_id="trace_abc",
    task_id="task_xyz",
    agent=agent.did,
    from_state="running",
    to_state="completed",
    cost_used=2.5,
    budget_remaining=97.5,
)
```

---

## Class: `StdoutSink`

**Module:** `agentpassport.observability.sinks`

```python
class StdoutSink(Sink):
    def write(self, event: ObservabilityEvent) -> None
```

Writes each event as a single line of compact JSON to `sys.stdout`, followed by a newline. Calls `sys.stdout.flush()` after each write.

**No constructor parameters.**

---

## Class: `FileSink`

**Module:** `agentpassport.observability.sinks`

```python
class FileSink(Sink):
    def __init__(self, path: Path) -> None
    def write(self, event: ObservabilityEvent) -> None
```

Appends each event as a JSON line to the specified file. Opens the file in append mode for each write (safe for external log rotation).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | `pathlib.Path` | Yes | Path to the NDJSON log file. Created if it doesn't exist. |

---

## Class: `MemorySink`

**Module:** `agentpassport.observability.sinks`

```python
class MemorySink(Sink):
    def __init__(self) -> None
    def write(self, event: ObservabilityEvent) -> None
    events: list[ObservabilityEvent]
```

Stores all events in `self.events` (a list). Useful in tests to assert what events were emitted.

**Example:**
```python
from agentpassport import Agent, TaskEnvelope, Intent, EventEmitter, MemorySink

sink = MemorySink()
agent = Agent(name="test", emitter=EventEmitter(sinks=[sink]))

@agent.capability("ping")
async def ping(task):
    return {"pong": True}

task = TaskEnvelope(intent=Intent(type="ping"))
await agent.handle(task)

assert [e.event for e in sink.events] == [
    "task_accepted", "task_running", "task_completed"
]
```

---

## Class: `OtelSink`

**Module:** `agentpassport.observability.otel`

```python
class OtelSink(Sink):
    def __init__(self, tracer: Any = None) -> None
    def write(self, event: ObservabilityEvent) -> None
```

Exports each `ObservabilityEvent` as an OpenTelemetry span.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tracer` | `opentelemetry.trace.Tracer \| None` | `None` | OTel tracer instance. If `None`, calls `trace.get_tracer("agentpassport")` using the globally configured tracer provider. |

**Raises (construction):** `ImportError` if `opentelemetry-api` is not installed and `tracer=None`.

**Span attributes set:**
- `agentpassport.trace_id`
- `agentpassport.task_id`
- `agentpassport.agent`
- `agentpassport.event`
- `agentpassport.cost_used`
- `agentpassport.budget_remaining`
- `agentpassport.from_state` (if set)
- `agentpassport.to_state` (if set)
- `agentpassport.meta.<key>` for each key in `event.metadata`

**Error handling:** `write()` catches all exceptions from OTel to prevent observability failures from crashing the agent.

**Installation:**
```bash
pip install agentpassport[otel]
# or
pip install agentpassport opentelemetry-api
```

**Example:**
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from agentpassport import Agent, EventEmitter, OtelSink

provider = TracerProvider()
trace.set_tracer_provider(provider)

sink = OtelSink()  # uses globally configured provider
agent = Agent(name="worker", emitter=EventEmitter(sinks=[sink]))
```

---

## Class: `TrustMiddleware`

**Module:** `agentpassport.trust`

```python
class TrustMiddleware:
    def __init__(
        self,
        agent_did: str,
        known_public_keys: dict[str, bytes],
        capability_scopes: dict[str, list[str]],
    ) -> None
```

Pre-execution scope enforcement. Wired automatically inside `Agent`. You typically don't need to instantiate this directly unless building a custom agent framework.

> **Python/TypeScript difference:** The TypeScript `TrustMiddleware` constructor accepts an optional `revocationRegistry` parameter. The Python version does not — pass `revocation_registry` to `verify_auth_chain()` directly instead.

### Constructor

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_did` | `str` | Yes | The DID of the agent whose scope is being checked. Tokens with `sub != agent_did` are ignored. |
| `known_public_keys` | `dict[str, bytes]` | Yes | Map from issuer DID to 32-byte public key. Passed by reference — mutations to the dict after construction are reflected in subsequent checks. |
| `capability_scopes` | `dict[str, list[str]]` | Yes | Map from capability name to required scope list. Passed by reference. |

### `TrustMiddleware.check()`

```python
def check(self, task_auth_chain: list[str], capability_name: str) -> None
```

Raises `ScopeError` if the auth chain doesn't cover the required scope for `capability_name`. No-op if the capability has no declared required scope.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_auth_chain` | `list[str]` | Yes | The `auth_chain` from the `TaskEnvelope`. |
| `capability_name` | `str` | Yes | The capability being invoked. |

**Raises:** `ScopeError` if scope check fails.

**Returns:** `None`

---

## Exception: `ScopeError`

**Module:** `agentpassport.trust`

```python
class ScopeError(Exception):
    pass
```

Raised by `TrustMiddleware.check()` and propagated through `Agent.handle()`. The message includes:
- The capability name
- The required scopes
- The granted scopes (or "no auth chain" if chain was empty)

**Example:**
```python
from agentpassport import ScopeError

try:
    await agent.handle(task)
except ScopeError as e:
    # e.args[0] is the message, e.g.:
    # "Capability 'read_customers' requires scope ['read:db:customers']
    #  not granted by the auth chain. Granted: ['write:cache']"
    return {"error": "forbidden", "detail": str(e)}
```

---

## Class: `TaskLifecycle`

**Module:** `agentpassport.task.lifecycle`

```python
class TaskLifecycle:
    def __init__(self, task: TaskEnvelope) -> None
    def transition(self, to_state: TaskState) -> None
    @property
    def is_terminal(self) -> bool
```

Enforces the task state machine. `Agent.handle()` uses this internally.

### Constructor

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | `TaskEnvelope` | Yes | The task whose state is managed. State changes mutate `task.state` in-place. |

### `TaskLifecycle.transition()`

```python
def transition(self, to_state: TaskState) -> None
```

Transition `task.state` to `to_state`.

**Raises:** `InvalidTransitionError` if the transition is not allowed.

**Returns:** `None`. Mutates `self.task.state`.

### `TaskLifecycle.is_terminal`

```python
@property
def is_terminal(self) -> bool
```

Returns `True` if `task.state` is `COMPLETED`, `FAILED`, or `CANCELLED`.

**Example:**
```python
from agentpassport import TaskLifecycle, TaskEnvelope, Intent, TaskState

task = TaskEnvelope(intent=Intent(type="ping"))
lc = TaskLifecycle(task)

lc.transition(TaskState.DELEGATED)
lc.transition(TaskState.ACCEPTED)
lc.transition(TaskState.RUNNING)
lc.transition(TaskState.COMPLETED)

assert lc.is_terminal is True
```

---

## Exception: `InvalidTransitionError`

**Module:** `agentpassport.task.lifecycle`

```python
class InvalidTransitionError(Exception):
    from_state: TaskState
    to_state: TaskState
```

Raised by `TaskLifecycle.transition()` when attempting a disallowed transition. Carries the source and target states.

**Example:**
```python
from agentpassport.task.lifecycle import InvalidTransitionError

try:
    lc.transition(TaskState.COMPLETED)
    lc.transition(TaskState.RUNNING)  # terminal → non-terminal: invalid
except InvalidTransitionError as e:
    print(f"Can't go {e.from_state} → {e.to_state}")
```

---

## Class: `BudgetTracker`

**Module:** `agentpassport.task.budget`

```python
class BudgetTracker:
    def __init__(self, total_credits: float) -> None
```

Tracks credit spending against a total budget. Not thread-safe for synchronous methods; use `async_spend` / `async_allocate` / `async_return_unused` in async contexts with concurrent access.

### Constructor

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `total_credits` | `float` | Yes | The total budget available. Must be non-negative (not validated at construction). |

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `total_credits` | `float` | Budget set at construction |
| `spent` | `float` | Credits spent so far |
| `remaining` | `float` (property) | `total_credits - spent` |

### `BudgetTracker.spend()`

```python
def spend(self, amount: float) -> None
```

Deduct `amount` from remaining budget.

**Raises:**
- `ValueError` if `amount < 0`
- `BudgetExceededError` if `amount > self.remaining`

### `BudgetTracker.allocate()`

```python
def allocate(self, amount: float) -> float
```

Reserve `amount` for a subtask. Returns the allocated amount.

**Raises:**
- `ValueError` if `amount < 0`
- `BudgetExceededError` if `amount > self.remaining`

### `BudgetTracker.return_unused()`

```python
def return_unused(self, amount: float) -> None
```

Return unused budget from a completed subtask. Decreases `self.spent` (clamped to 0).

**Raises:** `ValueError` if `amount < 0`

### `BudgetTracker.async_spend()`

```python
async def async_spend(self, amount: float) -> None
```

Thread-safe version of `spend()` using `asyncio.Lock`.

### `BudgetTracker.async_allocate()`

```python
async def async_allocate(self, amount: float) -> float
```

Thread-safe version of `allocate()` using `asyncio.Lock`.

### `BudgetTracker.async_return_unused()`

```python
async def async_return_unused(self, amount: float) -> None
```

Thread-safe version of `return_unused()` using `asyncio.Lock`.

**Example 1: Basic tracking**
```python
from agentpassport import BudgetTracker, BudgetExceededError

tracker = BudgetTracker(total_credits=100.0)
tracker.spend(20.0)
print(tracker.remaining)  # 80.0

tracker.spend(80.0)
print(tracker.remaining)  # 0.0

try:
    tracker.spend(1.0)
except BudgetExceededError as e:
    print(f"Over budget: requested {e.requested}, remaining {e.remaining}")
```

**Example 2: Subtask allocation and return**
```python
tracker = BudgetTracker(total_credits=100.0)

allocated = tracker.allocate(30.0)  # subtask gets 30 credits
# subtask only used 10
tracker.return_unused(20.0)

print(tracker.remaining)  # 90.0 (100 - 30 + 20)
```

**Example 3: Async concurrent access**
```python
import asyncio

tracker = BudgetTracker(total_credits=50.0)

async def worker(amount):
    try:
        await tracker.async_spend(amount)
        print(f"Spent {amount}, remaining {tracker.remaining}")
    except BudgetExceededError:
        print(f"Couldn't spend {amount} — over budget")

await asyncio.gather(
    worker(20.0),
    worker(20.0),
    worker(20.0),  # This one will fail
)
```

---

## Exception: `BudgetExceededError`

**Module:** `agentpassport.task.budget`

```python
class BudgetExceededError(Exception):
    requested: float
    remaining: float
```

Raised by `BudgetTracker.spend()` and `BudgetTracker.allocate()` (and their async variants) when the requested amount exceeds what's available.

---

## Function: `create_subtask()`

**Module:** `agentpassport.task.delegation`

```python
def create_subtask(
    parent: TaskEnvelope,
    intent: Intent,
    budget_credits: float,
    budget_tracker: BudgetTracker,
) -> TaskEnvelope
```

Create a child `TaskEnvelope` that inherits the parent's auth chain, trace ID, deadline, and remaining delegation depth (decremented by 1), with a new budget carved from the parent's tracker.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `parent` | `TaskEnvelope` | Yes | The parent task. Its `auth_chain`, `trace_id`, `deadline_ms`, `allowed_capabilities`, `denied_capabilities`, and transport are inherited. |
| `intent` | `Intent` | Yes | The subtask's intent (type and params). |
| `budget_credits` | `float` | Yes | Credits to allocate for the subtask from the parent's budget. |
| `budget_tracker` | `BudgetTracker` | Yes | The parent's budget tracker. `allocate(budget_credits)` is called on it. |

**Returns:** `TaskEnvelope` — a new task with:
- `parent_id = parent.id`
- `constraints.max_delegations = parent.constraints.max_delegations - 1`
- `constraints.budget_credits = budget_credits`
- Inherited: `auth_chain`, `trace_id`, `deadline_ms`, `allowed_capabilities`, `denied_capabilities`, `transport`

**Raises:**
- `ValueError` — if `parent.constraints.max_delegations <= 0`
- `BudgetExceededError` — if `budget_credits > tracker.remaining`

**Example 1: Create and dispatch a subtask**
```python
from agentpassport import (
    Agent, TaskEnvelope, Intent, BudgetTracker, create_subtask,
)

@agent.capability("orchestrate")
async def orchestrate(task: TaskEnvelope) -> dict:
    tracker = BudgetTracker(task.constraints.budget_credits)

    subtask = create_subtask(
        parent=task,
        intent=Intent(type="summarize", params={"text": "..."}),
        budget_credits=10.0,
        budget_tracker=tracker,
    )

    result = await agent.delegate(
        subtask,
        target_did=summarizer_did,
        endpoint="http://summarizer:8080",
        scope=["invoke:llm"],
    )
    return {"summary": result["summary"]}
```

**Example 2: Delegation depth exhausted**
```python
from agentpassport import TaskEnvelope, Intent, Constraints

task = TaskEnvelope(
    intent=Intent(type="root"),
    constraints=Constraints(max_delegations=0),
)
tracker = BudgetTracker(100.0)

try:
    create_subtask(task, Intent(type="sub"), 10.0, tracker)
except ValueError as e:
    print(e)  # "Cannot delegate: max_delegations exhausted"
```

---

## Class: `RevocationRegistry`

**Module:** `agentpassport.revocation`

Abstract base class. Implement this to build a custom revocation backend.

```python
from abc import ABC, abstractmethod

class RevocationRegistry(ABC):
    @abstractmethod
    def revoke(self, jti: str) -> None: ...

    @abstractmethod
    def is_revoked(self, jti: str) -> bool: ...
```

### `revoke(jti)`

Mark a JTI as revoked. Must be idempotent (calling twice has the same effect as once).

### `is_revoked(jti)`

Return `True` if the JTI has been revoked, `False` otherwise.

---

## Class: `InMemoryRevocationRegistry`

**Module:** `agentpassport.revocation`

```python
class InMemoryRevocationRegistry(RevocationRegistry):
    def __init__(self) -> None
    def revoke(self, jti: str) -> None
    def is_revoked(self, jti: str) -> bool
```

In-process revocation using a Python `set`. State is lost on restart. Suitable for tests and short-lived processes.

**Example:**
```python
from agentpassport import InMemoryRevocationRegistry

registry = InMemoryRevocationRegistry()
registry.revoke("some-uuid")
assert registry.is_revoked("some-uuid") is True
assert registry.is_revoked("other-uuid") is False
```

---

## Class: `SqliteRevocationRegistry`

**Module:** `agentpassport.revocation`

```python
class SqliteRevocationRegistry(RevocationRegistry):
    def __init__(self, db_path: str = "agentpassport_revocation.db") -> None
    def initialize(self) -> None
    def revoke(self, jti: str) -> None
    def is_revoked(self, jti: str) -> bool
```

Persistent revocation registry backed by SQLite. Must call `initialize()` before first use.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `"agentpassport_revocation.db"` | Path to the SQLite database file. Created if it doesn't exist. |

### `SqliteRevocationRegistry.initialize()`

Creates the `revoked_tokens` table if it doesn't exist. Safe to call multiple times.

**Example:**
```python
from agentpassport import SqliteRevocationRegistry

registry = SqliteRevocationRegistry(db_path="/var/lib/agent/revocation.db")
registry.initialize()

registry.revoke("token-jti-uuid")
assert registry.is_revoked("token-jti-uuid") is True
# Persists across restarts
```

---

## Class: `RegistryClient`

**Module:** `agentpassport.registry_client`

Client for the `agentpassport-registry` service. Allows agents to publish and discover agent cards.

```python
class RegistryClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None
    async def publish(self, card: AgentCard) -> dict
    async def get(self, did: str) -> AgentCard | None
    async def search(self, capability: str | None = None) -> list[AgentCard]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | required | Base URL of the registry service (e.g. `"http://registry:8000"`) |
| `timeout` | `float` | `10.0` | HTTP request timeout in seconds |

**Example:**
```python
from agentpassport import RegistryClient, sign_agent_card, AgentCard

client = RegistryClient("http://registry:8000")

card = AgentCard(
    did=agent.did,
    name="summarizer",
    capabilities=["summarize"],
    endpoint="http://summarizer:8080",
)
signed_card = sign_agent_card(card, private_key)
await client.publish(signed_card)

# Discover agents by capability
agents = await client.search(capability="summarize")
```

---

## Class: `HttpTransport`

**Module:** `agentpassport.transport.http`

```python
class HttpTransport(Transport):
    def __init__(self, base_url: str = "", timeout: float = 30.0) -> None
    def serialize(self, task: TaskEnvelope) -> bytes
    def deserialize(self, data: bytes) -> TaskEnvelope
    async def send(self, task: TaskEnvelope, endpoint: str) -> dict[str, Any]
```

HTTP transport using `httpx.AsyncClient`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | `""` | Base URL prepended to relative endpoint paths. |
| `timeout` | `float` | `30.0` | Request timeout in seconds. |

### `HttpTransport.serialize()`

Returns `task.model_dump_json().encode("utf-8")` — compact JSON bytes.

### `HttpTransport.deserialize()`

Returns `TaskEnvelope.model_validate_json(data)`.

### `HttpTransport.send()`

POSTs the serialized task to `<endpoint>/agentpassport/tasks` with `Content-Type: application/json`. If `endpoint` starts with `"http"`, it's used as-is; otherwise `base_url` is prepended.

**Raises:** `httpx.HTTPStatusError` on non-2xx responses, `httpx.RequestError` on network failures.

---

## Class: `StdioTransport`

**Module:** `agentpassport.transport.stdio`

```python
class StdioTransport(Transport):
    def serialize(self, task: TaskEnvelope) -> bytes
    def deserialize(self, data: bytes) -> TaskEnvelope
    async def send(self, task: TaskEnvelope, endpoint: str) -> dict[str, Any]
```

Stdio transport for process-to-process communication. Writes the serialized task as a line to `stdout` of a subprocess and reads the response line from `stdin`.

---

## Internal helpers (identity)

These are internal functions in `agentpassport.identity.did` and `agentpassport.identity.signing`. They are not exported from the top-level module but are documented here for completeness.

### `_base58btc_encode(data: bytes) -> str`

Pure Python base58btc encoder (no external dependency). Uses the Bitcoin/IPFS/W3C alphabet: `123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz`.

### `_base58btc_decode(s: str) -> bytes`

Inverse of `_base58btc_encode`.

### `_b64url_encode(data: bytes) -> str`

Standard base64url encoding with padding stripped. Used for JWT parts.

### `_b64url_decode(s: str) -> bytes`

Inverse of `_b64url_encode`. Re-adds padding before decoding.

### `_encode_jwt(claims: dict, private_key_seed: bytes) -> str`

Produces a compact EdDSA JWT. Signs `header.payload` with the 32-byte seed using PyNaCl. Claims are JSON-serialized with sorted keys (for cross-SDK compatibility).

### `_decode_jwt_claims(token: str) -> dict`

Decodes the payload section of a JWT **without verifying the signature**. Used internally to read `iss` before looking up the public key.

### `_verify_jwt_signature(token: str, public_key_bytes: bytes) -> dict`

Verifies the JWT signature and returns the decoded claims. Raises `ValueError` on structural issues, `nacl.exceptions.BadSignatureError` on invalid signatures.

### `_chain_granted_scopes(auth_chain, agent_did, known_public_keys) -> set[str]`

Returns the union of scopes from all valid, non-expired, correctly-targeted tokens in the chain. Used by `TrustMiddleware.check()`.
