# AgentPassport Documentation

## Overview

AgentPassport is a protocol and SDK for giving AI agents cryptographically verifiable identities and expressing who authorized whom to do what as tasks flow between agents.

Available in Python (`agentpassport`) and TypeScript (`@agentpassport/core`), with full cross-SDK wire compatibility.

---

## Documentation Index

### Conceptual Guide

**[concepts.md](./concepts.md)** — Start here. Covers every foundational idea deeply:
- Decentralized Identifiers (DIDs) and the `did:key` format
- Ed25519 keypairs: why, how, and wire format
- AgentCard: the signed identity document
- TaskEnvelope: the unit of work
- Delegation and the auth chain: mechanics with sequence diagrams
- JWT structure: header, claims, signing, key sorting
- Scope semantics: format, wildcard, matching rules, narrowing
- Trust middleware: how pre-execution checks work
- Revocation: soft-stop mechanics with ASCII sequence diagrams
- Task lifecycle state machine with ASCII state diagram
- Budget tracking and subtask trees
- Observability and event sinks
- Transport layer
- Registry
- Adapters (MCP, REST, CLI, A2A)
- Multi-SDK wire compatibility

---

### Python API Reference

| Document | Contents |
|----------|----------|
| **[python/api-reference.md](./python/api-reference.md)** | Every class, function, method, and type in `agentpassport`. Full parameter tables, return types, exceptions, and 2–3 examples per item. |
| **[python/adapters.md](./python/adapters.md)** | `McpAdapter`, `RestAdapter`, `CliAdapter`, `A2AServerAdapter`, `A2AClientAdapter` — bridge AgentPassport tasks to external services and protocols. |
| **[python/registry.md](./python/registry.md)** | Registry service HTTP API (`POST /v1/agents`, `GET /v1/agents/query`, etc.), `SqliteStorage`, `QueryEngine`, and `RegistryClient`. |

**Exported symbols covered in api-reference.md:**

- `Agent` (constructor, `.capability()`, `.trust_keys()`, `.delegate()`, `.handle()`)
- Identity: `generate_keypair()`, `did_from_public_key()`, `parse_did()`, `sign_delegation()`, `verify_auth_chain()`, `sign_agent_card()`, `verify_agent_card()`
- Types: `AgentCard`, `CostInfo`, `TaskEnvelope`, `Intent`, `Constraints`, `TaskState`, `ObservabilityEvent`
- Observability: `EventEmitter`, `StdoutSink`, `FileSink`, `MemorySink`, `OtelSink`
- Trust: `TrustMiddleware`, `ScopeError`
- Lifecycle: `TaskLifecycle`, `InvalidTransitionError`
- Budget: `BudgetTracker`, `BudgetExceededError`, `create_subtask()`
- Revocation: `RevocationRegistry`, `InMemoryRevocationRegistry`, `SqliteRevocationRegistry`
- Transport: `HttpTransport`, `StdioTransport`
- `RegistryClient`
- Internal helpers: `_base58btc_encode/decode`, `_b64url_encode/decode`, `_encode_jwt`, `_decode_jwt_claims`, `_verify_jwt_signature`, `_chain_granted_scopes`

---

### TypeScript API Reference

| Document | Contents |
|----------|----------|
| **[typescript/api-reference.md](./typescript/api-reference.md)** | Every exported symbol from `@agentpassport/core`. Full type signatures, parameter tables, return types, exceptions, and 2–3 examples per item. |

**Exported symbols covered:**

- Identity: `generateKeypair()`, `keypairFromSeed()`, `didFromPublicKey()`, `parseDid()`, `base58btcEncode()`, `base58btcDecode()`, `Keypair`
- JWT: `signDelegation()`, `verifyAuthChain()`, `decodeJwtClaims()`, `DelegationClaims`, `SignDelegationOptions`, `VerifyAuthChainOptions`
- Revocation: `InMemoryRevocationRegistry`, `RevocationRegistry`
- Trust: `TrustMiddleware`, `ScopeError`
- Agent: `Agent` (constructor, `.capability()`, `.trustKeys()`, `.handle()`, `.delegate()`), `CapabilityHandler`, `CapabilityOptions`, `DelegateOptions`
- Types: `createTask()`, `TaskEnvelope`, `TaskState`, `Intent`, `Constraints`
- Internal helpers: `b64urlEncode/Decode`, `encodeJwt`, `decodeJwtClaims`, `verifyJwtSignature`

---

### Guides (Runnable End-to-End Examples)

| Document | Contents |
|----------|----------|
| **[guides/python-quickstart.md](./guides/python-quickstart.md)** | 10 complete, copy-paste-runnable Python examples covering every major feature. |
| **[guides/typescript-quickstart.md](./guides/typescript-quickstart.md)** | 10 complete, copy-paste-runnable TypeScript examples covering every major feature. |

**Python guide steps:**
1. Single agent, local capability dispatch
2. Two agents with delegation and scope checking
3. Full HTTP server with FastAPI (production-ready)
4. Orchestrator that delegates to an HTTP worker
5. Three-hop delegation chain with scope narrowing
6. Budget tracking in a subtask tree
7. Revocation (issue, revoke, verify)
8. AgentCard signing, verification, and JSON round-trip
9. Observability with multiple sinks
10. Complete production example — all features combined

**TypeScript guide steps:**
1. Single agent, single capability
2. Two agents with delegation and ScopeError demo
3. HTTP server using Express
4. Orchestrator delegating to HTTP worker
5. Three-hop delegation chain with scope narrowing
6. Revocation with `InMemoryRevocationRegistry`
7. Cross-SDK compatibility: TypeScript verifying Python tokens
8. Complete production example — all features combined
9. Edge/serverless with Hono
10. Persistent identity: load or create keypair from disk

---

## Quick Reference

### Python — minimal working example

```python
from agentpassport import Agent, TaskEnvelope, Intent, sign_delegation, generate_keypair

# Two agents
orch_priv, orch_pub = generate_keypair()
orchestrator = Agent(name="orchestrator", private_key=orch_priv)
worker = Agent(name="worker")
worker.trust_keys({orchestrator.did: orchestrator.public_key})

# Register a scoped capability
@worker.capability("process", requires=["run:process"])
async def process(task: TaskEnvelope) -> dict:
    return {"result": "done"}

# Create task, delegate, handle
task = TaskEnvelope(intent=Intent(type="process", params={}))
token = sign_delegation(orch_priv, orchestrator.did, worker.did, ["run:process"])
task.auth_chain.append(token)

result = await worker.handle(task)
print(result)  # {'result': 'done'}
```

### TypeScript — minimal working example

```typescript
import { Agent, createTask, ScopeError } from "@agentpassport/core";

const orchestrator = new Agent("orchestrator");
const worker = new Agent("worker");
worker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });

worker.capability(
  "process",
  { requires: ["run:process"] },
  async () => ({ result: "done" })
);

const task = createTask({ type: "process", params: {} });
const delegated = orchestrator.delegate(task, {
  targetDid: worker.did,
  scope: ["run:process"],
});

const result = await worker.handle(delegated);
console.log(result);  // { result: 'done' }
```

---

## Package structure

```
packages/
├── agentpassport/          # Python core SDK
│   └── src/agentpassport/
│       ├── agent.py              # Agent class
│       ├── trust.py              # TrustMiddleware, ScopeError
│       ├── revocation.py         # RevocationRegistry implementations
│       ├── registry_client.py    # RegistryClient
│       ├── identity/
│       │   ├── did.py            # DID generation, base58btc
│       │   ├── signing.py        # JWT sign/verify, AgentCard signing
│       │   └── keystore.py       # Key persistence helpers
│       ├── task/
│       │   ├── lifecycle.py      # TaskLifecycle, state machine
│       │   ├── budget.py         # BudgetTracker
│       │   └── delegation.py     # create_subtask()
│       ├── observability/
│       │   ├── emitter.py        # EventEmitter
│       │   ├── sinks.py          # StdoutSink, FileSink, MemorySink
│       │   └── otel.py           # OtelSink
│       ├── transport/
│       │   ├── http.py           # HttpTransport
│       │   └── stdio.py          # StdioTransport
│       └── types/
│           ├── agent_card.py     # AgentCard, CostInfo
│           ├── task.py           # TaskEnvelope, Intent, Constraints, TaskState
│           ├── identity.py       # Auth chain notes
│           └── events.py         # ObservabilityEvent
│
├── agentpassport-adapters/ # Python adapters (MCP, REST, CLI, A2A)
│   └── src/agentpassport_adapters/
│       ├── base.py               # Adapter ABC
│       ├── mcp.py                # McpAdapter
│       ├── rest.py               # RestAdapter
│       └── cli.py                # CliAdapter
│
├── agentpassport-registry/ # Registry service (FastAPI + SQLite)
│   └── src/agentpassport_registry/
│       ├── app.py                # create_app() factory
│       ├── routes.py             # HTTP routes
│       ├── query.py              # QueryEngine
│       ├── limiter.py            # Rate limiter setup
│       └── storage/
│           ├── base.py           # Storage ABC
│           └── sqlite.py         # SqliteStorage
│
├── agentpassport-cli/      # CLI for managing agent identities
│   └── src/agentpassport_cli/
│       ├── main.py               # CLI entry point
│       ├── identity.py           # Identity commands
│       └── trace.py              # Trace inspection commands
│
└── agentpassport-ts/       # TypeScript SDK
    └── src/
        ├── index.ts              # Public exports
        ├── identity.ts           # DID, keypair, base58btc
        ├── jwt.ts                # JWT sign/verify
        ├── revocation.ts         # RevocationRegistry
        ├── trust.ts              # TrustMiddleware, ScopeError
        ├── agent.ts              # Agent class
        └── types.ts              # TaskEnvelope, Intent, Constraints, etc.
```
