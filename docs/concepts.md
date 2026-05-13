# AgentPassport — Core Concepts

This document explains the foundational ideas behind AgentPassport: what it does, why each piece exists, and how the pieces fit together. Read this before the API reference.

---

## Table of Contents

1. [What is AgentPassport?](#1-what-is-agentpassport)
2. [Decentralized Identifiers (DIDs)](#2-decentralized-identifiers-dids)
3. [Ed25519 Keypairs](#3-ed25519-keypairs)
4. [AgentCard — Agent Identity Document](#4-agentcard--agent-identity-document)
5. [TaskEnvelope — The Unit of Work](#5-taskenvelope--the-unit-of-work)
6. [Delegation and the Auth Chain](#6-delegation-and-the-auth-chain)
7. [JWT Structure](#7-jwt-structure)
8. [Scope Semantics](#8-scope-semantics)
9. [Trust Middleware](#9-trust-middleware)
10. [Revocation Mechanics](#10-revocation-mechanics)
11. [Task Lifecycle State Machine](#11-task-lifecycle-state-machine)
12. [Budget Tracking](#12-budget-tracking)
13. [Observability and Event Sinks](#13-observability-and-event-sinks)
14. [Transport Layer](#14-transport-layer)
15. [Registry](#15-registry)
16. [Adapters — MCP, REST, CLI](#16-adapters--mcp-rest-cli)
17. [Multi-SDK Wire Compatibility](#17-multi-sdk-wire-compatibility)

---

## 1. What is AgentPassport?

AgentPassport is a protocol and SDK for giving AI agents **cryptographically verifiable identities** and for expressing **who authorized whom to do what** as tasks flow between agents.

Without AgentPassport, when Agent B receives a task from Agent A saying "please read the customer database," there is no way for B to verify:
- That A is who it claims to be
- That A was itself authorized to delegate this task
- That the permission hasn't been revoked

AgentPassport solves this with three interlocking mechanisms:

1. **DID-based identity** — Every agent has a globally unique, self-certifying identifier derived from its public key. No central authority needed.
2. **JWT delegation chains** — Each time a task is delegated, the delegating agent cryptographically signs a token that records who it is, who it's delegating to, what scopes are granted, and when it expires.
3. **Pre-execution scope checks** — Before any capability handler runs, the receiving agent verifies the full chain of custody and checks that the required permissions are present.

---

## 2. Decentralized Identifiers (DIDs)

### Format

AgentPassport uses the `did:key` DID method defined by the W3C. A DID looks like:

```
did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK
```

Breaking it down:
- `did:` — the DID scheme prefix
- `key:` — the DID method (self-certifying: the key *is* the identifier)
- `z` — the multibase prefix for base58btc encoding
- The rest — a base58btc-encoded blob that encodes both the key type and the key material

### Encoding a public key into a DID

```
Ed25519 public key (32 bytes)
    → Prepend multicodec prefix 0xed 0x01 (2 bytes) → 34 bytes total
    → Base58btc encode
    → Prepend "z" (multibase prefix for base58btc)
    → Prepend "did:key:"
```

The multicodec prefix `0xed01` is a varint-encoded identifier that means "Ed25519 public key" in the multicodec registry. This prefix allows future support for other key types without changing the DID method.

### Why base58btc?

Base58btc (the Bitcoin/IPFS variant) omits characters that are visually ambiguous (`0`, `O`, `I`, `l`) and avoids URL-unsafe characters. It's URL-safe and human-readable enough to appear in logs.

### Deriving identity

Because the DID is derived from the public key, **generating a keypair is the same as creating an identity**. There's no registration step and no central authority. Any agent that holds the private key corresponding to the DID is definitionally that agent.

### ASCII diagram

```
generate_keypair()
    ↓
  private key (32-byte Ed25519 seed)
  public key  (32-byte Ed25519 verify key)
    ↓
did_from_public_key(public_key)
    ↓
  [0xED, 0x01] + public_key bytes
    ↓ base58btc encode
  z6Mk...
    ↓
  "did:key:z6Mk..."
```

---

## 3. Ed25519 Keypairs

AgentPassport uses **Ed25519** (Edwards-curve Digital Signature Algorithm) for all signing operations.

### Why Ed25519?

- **Small keys**: 32-byte private keys, 32-byte public keys, 64-byte signatures
- **Fast**: signing and verification are faster than RSA-2048 and comparable to ECDSA P-256
- **Secure**: resists side-channel attacks; deterministic signatures avoid random-number bugs
- **Standardized**: used in TLS 1.3, SSH, Signal, and the W3C DID ecosystem

### Key layout

AgentPassport represents a keypair as two separate byte strings:

| Field | Length | Contents |
|-------|--------|----------|
| `private_key` | 64 bytes | First 32 bytes: Ed25519 seed. Last 32 bytes: public key bytes (mirror of public_key). |
| `public_key` | 32 bytes | Ed25519 verify key |

The 64-byte layout matches PyNaCl's convention and is mirrored in the TypeScript SDK for wire compatibility.

When signing, only the first 32 bytes of `private_key` (the seed) are passed to the signing function. The seed deterministically derives the full Ed25519 scalar.

---

## 4. AgentCard — Agent Identity Document

An `AgentCard` is a signed, shareable document describing an agent: what it can do, where it lives, and what it costs.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `did` | `str` | Yes | The agent's DID, derived from its public key |
| `name` | `str` | Yes | Human-readable agent name |
| `version` | `str` | No (default `"0.1.0"`) | Agent version string |
| `capabilities` | `list[str]` | Yes | List of capability names the agent handles |
| `input_schema` | `dict` | No | JSON Schema for task input params |
| `output_schema` | `dict` | No | JSON Schema for task output |
| `cost` | `CostInfo` | No | Pricing metadata |
| `latency_p99_ms` | `int \| None` | No | 99th-percentile latency hint |
| `trust_requirements` | `list[str]` | No | Scope strings the agent requires callers to hold |
| `transports` | `list[str]` | No (default `["http"]`) | Supported transport protocols |
| `endpoint` | `str` | Yes | URL where the agent accepts tasks |
| `signature` | `str \| None` | No | Hex-encoded Ed25519 signature over `canonical_payload()` |

### Canonical payload and signing

The signature covers a deterministic SHA-256 hash of a compact JSON object containing four fields: `name`, `did`, `capabilities` (sorted), and `endpoint`. Mutable metadata like `cost`, `version`, and `latency` are intentionally excluded so they can be updated without invalidating the identity claim.

```
canonical_payload() =
  SHA-256(
    JSON.stringify(
      { capabilities: sorted(capabilities), did, endpoint, name },
      { sort_keys: true, separators: (',', ':') }
    )
  )
```

This means two parties can independently agree on the binding between an agent's name, its DID, its endpoint, and its capabilities — without trusting the transmission medium.

---

## 5. TaskEnvelope — The Unit of Work

A `TaskEnvelope` is the container passed between agents. It carries the intent, constraints, authorization chain, and lifecycle state.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | `str` | `"1.0"` | Protocol version |
| `id` | `str` | auto UUID | Unique task identifier (e.g. `task_a3f9...`) |
| `parent_id` | `str \| None` | `None` | ID of parent task (for subtask chains) |
| `intent` | `Intent` | required | What to do and with what parameters |
| `constraints` | `Constraints` | default | Budget, deadline, and delegation limits |
| `auth_chain` | `list[str]` | `[]` | Ordered list of delegation JWT strings |
| `result_schema` | `dict \| None` | `None` | Expected output JSON Schema |
| `trace_id` | `str` | auto UUID | Trace identifier for distributed tracing |
| `transport` | `str` | `"http"` | Transport hint |
| `state` | `TaskState` | `CREATED` | Current lifecycle state |

### Intent

```python
class Intent(BaseModel):
    type: str           # The capability name to invoke
    params: dict        # Parameters passed to the handler
```

### Constraints

```python
class Constraints(BaseModel):
    budget_credits: float       # Total credit budget (default 100.0, must be >= 0)
    deadline_ms: int | None     # Deadline timestamp in milliseconds since epoch
    max_delegations: int        # Maximum delegation depth remaining (default 10)
    allowed_capabilities: list[str]   # Whitelist of allowed capability names
    denied_capabilities: list[str]    # Blacklist of denied capability names
```

The `max_delegations` field decrements by 1 each time a subtask is created via `create_subtask()`. When it reaches 0, further delegation is rejected. This prevents runaway delegation chains.

### How tasks flow

```
Orchestrator creates TaskEnvelope
    → Orchestrator signs delegation JWT, appends to auth_chain
    → Orchestrator sends task to Agent A
        → Agent A verifies auth_chain
        → Agent A runs capability handler
        → (Optional) Agent A creates subtask with reduced budget
            → Agent A signs delegation JWT, appends to auth_chain
            → Agent A sends subtask to Agent B
                → Agent B verifies auth_chain
                → Agent B runs capability handler
```

---

## 6. Delegation and the Auth Chain

### The Problem

When Agent C receives a task that was originally created by User U and has passed through Agents A and B, how does C know:
- That U authorized A to start this workflow?
- That A authorized B to delegate further?
- That B authorized C for the specific capability being invoked?

### The Solution: Chained JWTs

Each delegation hop produces one JWT. The `auth_chain` field of a `TaskEnvelope` is a list of these JWTs in order:

```
auth_chain = [
    JWT(iss=U, sub=A, scope=["*"]),         # U delegated to A
    JWT(iss=A, sub=B, scope=["read:db"]),   # A delegated to B (narrowed scope)
    JWT(iss=B, sub=C, scope=["read:db"]),   # B delegated to C
]
```

### Verification rules

`verify_auth_chain()` checks every token in the chain:

1. **Structural validity**: The JWT must have exactly 3 parts (header.payload.signature).
2. **Algorithm check**: The header must declare `alg: EdDSA`.
3. **Issuer resolution**: The `iss` claim must be in `known_public_keys`.
4. **Cryptographic verification**: The signature must be valid under the issuer's public key.
5. **Temporal validity**: `iat <= now <= exp`.
6. **JTI presence**: The `jti` claim must be non-empty (required for revocation).
7. **Revocation check**: If a `RevocationRegistry` is provided, `jti` must not be revoked.
8. **Subject check**: The last token's `sub` must equal `expected_subject` (the receiving agent's DID).

### ASCII sequence diagram

```
User (U)                Agent A               Agent B               Agent C
  |                        |                     |                     |
  |-- creates task ------->|                     |                     |
  |   auth_chain=[]        |                     |                     |
  |                        |                     |                     |
  |                        |-- sign_delegation-->|                     |
  |                        |   iss=U.did         |                     |
  |                        |   sub=A.did         |                     |
  |                        |   scope=["*"]       |                     |
  |                        |                     |                     |
  |                        |-- send task ------->|                     |
  |                        |   auth_chain=[JWT1] |                     |
  |                        |                     |                     |
  |                        |                     |-- verify chain --   |
  |                        |                     |   JWT1 ok           |
  |                        |                     |                     |
  |                        |                     |-- sign_delegation-->|
  |                        |                     |   iss=A.did         |
  |                        |                     |   sub=B.did         |
  |                        |                     |   scope=["read:db"] |
  |                        |                     |                     |
  |                        |                     |-- send subtask ---->|
  |                        |                     |   auth_chain=       |
  |                        |                     |   [JWT1, JWT2]      |
  |                        |                     |                     |
  |                        |                     |                     |-- verify chain
  |                        |                     |                     |   JWT1: U->A ok
  |                        |                     |                     |   JWT2: A->B ok
  |                        |                     |                     |   sub=B.did ✓
```

### Scope narrowing

A key property: **scope can only narrow, never expand, as it travels down the chain**. If JWT1 grants `scope=["read:db"]`, then B cannot create a token with `scope=["write:db"]` and have it be useful — C would reject it because C checks that the chain grants the required scope, and the chain would not contain `write:db` from the root.

AgentPassport's scope check (`TrustMiddleware.check()`) operates on the union of scopes across all tokens whose subject is the agent being checked. This means a narrowed scope in the final hop is what C actually sees.

---

## 7. JWT Structure

AgentPassport uses compact JWTs with the EdDSA algorithm profile. The format is identical between the Python and TypeScript SDKs.

### Header

```json
{"alg":"EdDSA","crv":"Ed25519"}
```

This is constant. It does not contain a `kid` (key ID) because the issuer DID in the payload serves as the key reference.

### Payload (delegation claims)

```json
{
  "iss": "did:key:z6Mk...",
  "sub": "did:key:z6Mk...",
  "iat": 1717123456,
  "exp": 1717127056,
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "scope": ["read:db:customers", "write:cache"],
  "max_delegations": 3
}
```

| Claim | Type | Description |
|-------|------|-------------|
| `iss` | string | Issuer DID — the agent signing this delegation |
| `sub` | string | Subject DID — the agent being authorized |
| `iat` | integer | Issued-at Unix timestamp (seconds) |
| `exp` | integer | Expiry Unix timestamp (seconds) |
| `jti` | string | UUID4 unique token ID (required for revocation) |
| `scope` | array of strings | Permissions granted by this hop |
| `max_delegations` | integer | How many further delegation hops the subject may make |

### Signature

The signature is computed over the bytes of `<base64url(header)>.<base64url(payload)>` using the issuer's Ed25519 private key. The signature is then base64url-encoded without padding.

### Key sorting

The payload JSON is serialized with **sorted keys** (`sort_keys=True` in Python, `Object.keys().sort()` in TypeScript). This is essential for wire compatibility: both SDKs produce identical payloads for identical claims.

### Wire example

```
eyJhbGciOiJFZERTQSIsImNydiI6IkVkMjU1MTkifQ
.
eyJleHAiOjE3MTcxMjcwNTYsImlzcyI6ImRpZDprZXk6ejZNay4uLiIsIml
hdCI6MTcxNzEyMzQ1NiwianRpIjoiNTUwZTg0MDAtZTI5Yi00MWQ0LWE3MTY
tNDQ2NjU1NDQwMDAwIiwibWF4X2RlbGVnYXRpb25zIjozLCJzY29wZSI6WyJ
yZWFkOmRiOmN1c3RvbWVycyJdLCJzdWIiOiJkaWQ6a2V5OnooTk1rLi4uIn0
.
<64-byte Ed25519 signature, base64url-encoded>
```

---

## 8. Scope Semantics

Scopes are simple strings. AgentPassport imposes minimal structure so teams can adopt any naming convention that works for them.

### Recommended format

```
action:resource[:sub-resource]
```

Examples:
- `read:db` — read any database
- `write:db:customers` — write the customers table
- `read:cache` — read the cache
- `invoke:llm:gpt-4` — call GPT-4

### Wildcard

The special scope string `"*"` grants permission to any scope. A token with `scope: ["*"]` grants the subject all permissions.

### Matching rules

Matching is **exact or wildcard only**. There are no glob patterns, no prefix matching, no hierarchy:

| Granted | Required | Match? |
|---------|----------|--------|
| `*` | anything | ✓ Yes |
| `read:db` | `read:db` | ✓ Yes |
| `read:db` | `read:db:customers` | ✗ No |
| `read:db:customers` | `read:db` | ✗ No |
| `read:db` | `write:db` | ✗ No |

This strict matching is intentional: it forces issuers to be explicit about what they grant. Implicit scope inheritance through prefix matching would make it easy to accidentally grant too much.

### Multiple scopes

A token can grant multiple scopes: `scope: ["read:db", "write:cache", "invoke:llm"]`. The receiving agent's granted scopes are the **union** of all scopes across all valid tokens in the chain whose subject is that agent.

### Declaring required scopes on capabilities

```python
@agent.capability("summarize", requires=["invoke:llm", "read:docs"])
async def summarize(task):
    ...
```

If the auth chain grants `["*"]` or contains both `"invoke:llm"` and `"read:docs"`, the check passes. If either is missing, `ScopeError` is raised before the handler is called.

---

## 9. Trust Middleware

`TrustMiddleware` is the pre-execution gate that enforces scope declarations. It is wired automatically inside `Agent.handle()`.

### How it works

When `Agent.handle(task)` is called:

1. Look up the capability handler by `task.intent.type`.
2. Call `TrustMiddleware.check(task.auth_chain, capability_name)`.
3. If the capability declared `requires=[...]`:
   a. If `auth_chain` is empty → raise `ScopeError`.
   b. Iterate each token in `auth_chain`:
      - Skip tokens whose `sub` is not this agent's DID.
      - Skip tokens whose issuer is not in `known_public_keys`.
      - Verify the signature.
      - Skip expired tokens.
      - Accumulate valid scopes into a granted set.
   c. If `"*"` is in granted → pass.
   d. If any required scope is missing from granted → raise `ScopeError` with details.
4. If check passes, call the capability handler.

### ScopeError

`ScopeError` is a subclass of `Exception`. When raised, it carries:
- The capability name
- The required scopes
- The granted scopes (for debugging)
- A human-readable message

`Agent.handle()` does **not** catch `ScopeError` — it propagates to the caller. The caller (e.g. an HTTP server wrapping the agent) should catch it and return a `403 Forbidden` response.

### No required scope = always allowed

If a capability is registered without `requires=`, the middleware is a no-op for that capability. This allows unguarded capabilities for public or trusted-network-only deployments.

---

## 10. Revocation Mechanics

### Why revocation?

JWTs are stateless: once issued, a valid JWT is accepted until it expires. If a delegation should be stopped before expiry (agent compromised, task cancelled, user revoked consent), there must be a way to reject the token.

AgentPassport implements **soft revocation**: the agent completes its current atomic operation and stops before accepting new tasks. This is the standard model for stateless JWT revocation.

### How it works

Every delegation JWT carries a `jti` (JWT ID) claim — a UUID4. To revoke a delegation:

1. Obtain the `jti` from the JWT (decode without verifying: `_decode_jwt_claims(token)["jti"]`).
2. Call `registry.revoke(jti)`.
3. On the next call to `verify_auth_chain(...)`, the revocation registry is checked for each token's `jti`. If revoked, `verify_auth_chain` returns `False`.

### RevocationRegistry implementations

**InMemoryRevocationRegistry**: State lives in a Python set. Lost on restart. Good for testing and short-lived agents.

**SqliteRevocationRegistry**: Persists to a SQLite database. Survives restarts. Suitable for production.

### ASCII revocation sequence

```
Orchestrator                  Registry                Agent B
     |                            |                      |
     |-- registry.revoke(jti) -->|                      |
     |                            |-- INSERT jti ------>|
     |                            |   (persisted)        |
     |                            |                      |
     |                     [later]|                      |
     |                            |                      |
  Agent A                         |                      |
     |                            |                      |
     |-- send task to B --------------------------->    |
     |   (auth_chain contains revoked jti)              |
     |                            |                      |
     |                            |          verify_auth_chain()
     |                            |<-- is_revoked(jti) --|
     |                            |-- True ------------->|
     |                            |                      |
     |                      <-- task rejected (returns False) --|
```

### Revocation and TTL

Revocation is complementary to short-lived tokens. Best practice:
- Use short `ttl_seconds` (e.g. 3600 = 1 hour) to minimize the window during which a revocation is necessary.
- Use revocation for immediate stop when a token must be invalidated before its natural expiry.

---

## 11. Task Lifecycle State Machine

Every task has a `state` field that follows a strict finite state machine.

### States

| State | Meaning |
|-------|---------|
| `CREATED` | Task just created, not yet sent |
| `DELEGATED` | Task has been signed and dispatched to another agent |
| `ACCEPTED` | Receiving agent has verified the auth chain and accepted the task |
| `RUNNING` | Capability handler is executing |
| `COMPLETED` | Handler returned successfully |
| `FAILED` | Handler raised an exception |
| `CANCELLED` | Task was cancelled before completion |

### Allowed transitions

```
CREATED → DELEGATED, CANCELLED
DELEGATED → ACCEPTED, FAILED, CANCELLED
ACCEPTED → RUNNING, FAILED, CANCELLED
RUNNING → COMPLETED, FAILED, CANCELLED
COMPLETED → (terminal — no transitions)
FAILED → (terminal — no transitions)
CANCELLED → (terminal — no transitions)
```

### ASCII state diagram

```
         ┌──────────┐
         │  CREATED │
         └────┬─────┘
              │         ┌──────────────┐
              ├─────────→  DELEGATED   │
              │         └──────┬───────┘
              │                │         ┌─────────┐
              │                ├─────────→ ACCEPTED │
              │                │         └────┬─────┘
              │                │              │
              │                │              ├────────────────┐
              │                │              │                │
              │                │         ┌───▼────┐     ┌─────▼──────┐
              │                │         │ RUNNING│     │  FAILED    │
              │                │         └───┬────┘     └────────────┘
              │                │             │
              │                │       ┌─────▼───────┐
              │                │       │  COMPLETED  │
              │                │       └─────────────┘
              │                │
              └────────────────┴─────────────→ CANCELLED (from any non-terminal)
```

### InvalidTransitionError

Attempting a disallowed state transition raises `InvalidTransitionError` (from `task.lifecycle`). This is primarily an internal guard — `Agent.handle()` uses `TaskLifecycle` internally and will raise this if the lifecycle is manipulated incorrectly.

---

## 12. Budget Tracking

`BudgetTracker` enforces credit limits on task execution and subtask creation.

### Credits model

Credits are an abstract unit. The caller sets a `budget_credits` in `Constraints`. As the agent performs work (calling LLMs, querying databases, etc.), it calls `tracker.spend(amount)` to deduct from the budget. When a subtask is created, `allocate(amount)` reserves that portion of the budget.

### Thread safety

The async variants (`async_spend`, `async_allocate`, `async_return_unused`) acquire an `asyncio.Lock()` before modifying the `spent` counter. The synchronous variants are not thread-safe by themselves.

### BudgetExceededError

Raised when a `spend()` or `allocate()` call would take `spent > total_credits`. Contains `requested` and `remaining` float fields.

### Budget in subtask chains

When creating a subtask with `create_subtask()`:
- `budget_tracker.allocate(budget_credits)` is called, reducing the parent's remaining budget.
- The subtask's `Constraints.budget_credits` is set to the allocated amount.
- If the subtask completes with leftover budget, call `budget_tracker.return_unused(leftover)` to reclaim it.

---

## 13. Observability and Event Sinks

### EventEmitter

`EventEmitter` is a simple fan-out event bus. Agents emit structured `ObservabilityEvent` objects that are written to all registered sinks.

### ObservabilityEvent fields

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | `str` | Trace identifier for distributed tracing correlation |
| `task_id` | `str` | Task that produced this event |
| `event` | `str` | Event name (e.g. `task_accepted`, `task_completed`, `state_change`) |
| `from_state` | `str \| None` | Previous state (for `state_change` events) |
| `to_state` | `str \| None` | New state (for `state_change` events) |
| `agent` | `str` | DID of the agent emitting the event |
| `timestamp` | `str` | ISO 8601 UTC timestamp |
| `cost_used` | `float` | Credits spent so far |
| `budget_remaining` | `float` | Credits remaining |
| `metadata` | `dict` | Arbitrary key-value pairs |

### Built-in sinks

| Sink | Description |
|------|-------------|
| `StdoutSink` | Writes NDJSON to stdout (one event per line) |
| `FileSink` | Appends NDJSON to a file |
| `MemorySink` | Stores events in a list (for testing and inspection) |
| `OtelSink` | Emits OpenTelemetry spans (requires `opentelemetry-api`) |

### Events emitted by Agent.handle()

| Event name | When |
|-----------|------|
| `task_accepted` | After auth chain verified, before handler called |
| `task_running` | Handler about to be called |
| `task_completed` | Handler returned successfully |
| `task_failed` | Handler raised an exception |

---

## 14. Transport Layer

### HttpTransport

`HttpTransport` serializes a `TaskEnvelope` to JSON and POSTs it to `<endpoint>/agentpassport/tasks`. It uses `httpx.AsyncClient` for async HTTP.

### StdioTransport

`StdioTransport` serializes tasks to newline-delimited JSON over stdin/stdout. Used for process-based agent communication.

### Serialization format

Both transports use `TaskEnvelope.model_dump_json()` (Pydantic v2) which produces compact JSON. The `auth_chain` is a JSON array of JWT strings.

---

## 15. Registry

`RegistryClient` talks to the `agentpassport-registry` service — a central (but optional) directory of agent cards.

Agents can **publish** their `AgentCard` to the registry, and orchestrators can **look up** agents by DID or by capability name. The registry validates the card's signature before storing it.

The registry itself is a FastAPI app backed by SQLite, with optional rate limiting.

---

## 16. Adapters — MCP, REST, CLI

Adapters bridge AgentPassport's `TaskEnvelope` protocol to external services that don't speak AgentPassport natively.

### McpAdapter

Translates a `TaskEnvelope` into a JSON-RPC 2.0 `tools/call` request sent to an MCP (Model Context Protocol) server over stdio. The `task.intent.type` becomes the tool name, and `task.intent.params` become the arguments.

### RestAdapter

Translates a `TaskEnvelope` into a REST HTTP call. Maps intent type to an HTTP method and URL template.

### CliAdapter

Translates a `TaskEnvelope` into a subprocess invocation, passing params as CLI arguments or environment variables.

---

## 17. Multi-SDK Wire Compatibility

The Python SDK (`agentpassport`) and TypeScript SDK (`@agentpassport/core`) are designed to be fully wire-compatible. A task created in Python can be verified in TypeScript and vice versa.

### Compatibility guarantees

| Aspect | Guarantee |
|--------|-----------|
| DID format | Identical: `did:key:z<base58btc>`. Same multicodec prefix (0xed01). Same alphabet. |
| JWT header | Identical: `{"alg":"EdDSA","crv":"Ed25519"}`. Same base64url encoding. |
| JWT payload | Identical: JSON with sorted keys, compact separators (no spaces). |
| Signature | Identical: Ed25519 over `<header>.<payload>` bytes. |
| TaskEnvelope JSON | Identical field names, identical defaults, compatible Pydantic/TypeScript types. |

### Testing cross-SDK

```python
# Python: create a delegation token
from agentpassport import generate_keypair, did_from_public_key, sign_delegation
priv, pub = generate_keypair()
did = did_from_public_key(pub)
token = sign_delegation(priv, did, other_did, ["read:db"])
```

```typescript
// TypeScript: verify that token
import { verifyAuthChain } from "@agentpassport/core";
const ok = verifyAuthChain({
  chain: [token],
  expectedSubject: otherDid,
  knownPublicKeys: new Map([[issuerDid, issuerPubKey]]),
});
// ok === true
```
