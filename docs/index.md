# agentpassport

**The authorization primitive for multi-agent systems.**

When agents delegate work to other agents, there is no standard way to prove:
- That the receiving agent was actually authorized to act
- That it stayed within the scope it was granted
- That the authorization can be revoked mid-flight

agentpassport solves this with cryptographic proof of delegation at every hop — using standard primitives (Ed25519, JWT, W3C DIDs) that any language can verify.

**The single question agentpassport answers:** *Did this agent have the right to do that — and can you prove it?*

---

## How it works in one picture

```
Human / Orchestrator
  │
  │  signs JWT: scope=["read:db:customers"]
  ▼
Agent A (Python)  ──────────────────────────────────────────────────────────
  │                                                                         │
  │  verifies chain, appends own JWT                                        │
  ▼                                                                 ScopeError ✅
Agent B (TypeScript)    <── write:db:customers ──  rejected before handler runs
  │
  │  verifies full chain, dispatches handler
  ▼
capability: queryCustomers  ✅
```

Each agent in the chain:
1. Verifies every JWT in the `auth_chain` cryptographically
2. Checks that the chain grants the scope required by the capability
3. Optionally adds its own JWT before delegating further

---

## Install

### Python

```bash
pip install agentpassport
```

Python 3.11+ required. Core dependencies: `pydantic`, `PyNaCl`, `httpx`.

With OpenTelemetry support:

```bash
pip install agentpassport[otel]
```

### TypeScript / JavaScript

```bash
npm install @agentpassport/core
# or
pnpm add @agentpassport/core
# or
yarn add @agentpassport/core
```

Node.js 18+ required. ESM-only package. Core dependency: `@noble/ed25519`, `@noble/hashes`.

---

## 60-second example

```python
# Python
from agentpassport import Agent, TaskEnvelope, Intent

orchestrator = Agent("orchestrator")
worker = Agent("worker")

# Worker trusts orchestrator
worker.trust_keys({orchestrator.did: orchestrator.public_key})

# Orchestrator registers a capability — no scope required
@orchestrator.capability("run")
async def run(task: TaskEnvelope) -> dict:
    # Delegate to worker with narrowed scope — returns the worker's response dict
    result = await orchestrator.delegate(
        task,
        target_did=worker.did,
        endpoint="http://localhost:8001/task",
        scope=["read:db"],
    )
    return result

# Worker registers a scoped capability
@worker.capability("query", requires=["read:db"])
async def query(task: TaskEnvelope) -> dict:
    return {"rows": []}
```

```typescript
// TypeScript
import { Agent, createTask } from "agentpassport";

const orchestrator = new Agent("orchestrator");
const worker = new Agent("worker");

// Worker trusts orchestrator
worker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });

worker.capability(
  "query",
  { requires: ["read:db"] },
  async (task) => ({ rows: [] })
);
```

---

## Package overview

| Package | Language | Description |
|---------|----------|-------------|
| `agentpassport` | Python | Core SDK — identity, auth chain, trust, tasks |
| `agentpassport` (npm) | TypeScript | Wire-compatible TS SDK |
| `agentpassport-cli` | Python | CLI — `agentpass trace show`, key management (`ap` for short) |
| `agentpassport-registry` | Python | Optional agent registry server |
| `agentpassport-adapters` | Python | MCP, REST, CLI, and A2A adapters |

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Concepts](./concepts.md) | DID identity, auth chain, delegation, scope, trust middleware, revocation |
| [Python API Reference](./python/api-reference.md) | Every exported class and function in the Python SDK |
| [TypeScript API Reference](./typescript/api-reference.md) | Every exported class and function in the TypeScript SDK |
| [Python Adapters](./python/adapters.md) | MCP middleware, REST adapter, CLI adapter, A2A adapter |
| [Guide: Python Quickstart](./guides/python-quickstart.md) | Full runnable Python multi-agent walkthrough |
| [Guide: TypeScript Quickstart](./guides/typescript-quickstart.md) | Full runnable TypeScript multi-agent walkthrough |
| [Guide: Cross-SDK Interop](./guides/cross-sdk.md) | Python signs → TypeScript verifies, and vice versa |
| [Guide: MCP Middleware](./guides/mcp.md) | Enforce passport and scope before MCP tool execution |
| [Guide: A2A Integration](./guides/a2a.md) | Expose agentpassport agents as A2A servers; delegate to external A2A agents |

---

## Design principles

**1. Prove, don't trust.**
Every other framework assumes agents act within scope. agentpassport gives you cryptographic proof they did — or rejects them before they can act.

**2. Local root of trust.**
There is no global registry. The deploying entity (human, org, CI/CD) is the root of trust. Trust is local and explicit, like TLS.

**3. Scope can only narrow.**
A delegation chain can never expand permissions. If the root grants `read:db`, no hop downstream can claim `write:db`.

**4. Standard primitives.**
Ed25519 keys, W3C `did:key` DIDs, compact JWTs with EdDSA. Any language, any platform can verify a token — no agentpassport library required to read the wire format.

**5. Wire-compatible across languages.**
The Python and TypeScript SDKs produce identical tokens. A Python orchestrator can delegate to a TypeScript agent and vice versa — signatures verify across SDKs.
