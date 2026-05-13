# agentpassport

[![PyPI](https://img.shields.io/pypi/v/agentpassport)](https://pypi.org/project/agentpassport/)
[![npm](https://img.shields.io/npm/v/@agentpassport/core)](https://www.npmjs.com/package/@agentpassport/core)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**The AI passport layer.**

Agents are flooding the internet. They're sending emails, making purchases, running code — on your behalf, or someone else's. But there's no standard way to prove who an agent belongs to, what it's authorized to do, or whether it stayed within bounds.

agentpassport is building that. Starting with the authorization primitive — cryptographic proof of delegation at every hop. Growing into full agent identity and ownership verification across the open web.

**Today:** prove an agent was authorized to act.
**Next:** prove who it belongs to.

```
[Python Orchestrator] signs delegation → [TypeScript Agent] verifies before executing
         ↓
    ScopeError: requires [write:db:customers], granted [read:db:customers]  ✅
```

## Install

```bash
# Python
pip install agentpassport

# TypeScript / JavaScript
npm install @agentpassport/core
```

- [agentpassport on PyPI](https://pypi.org/project/agentpassport/)
- [@agentpassport/core on npm](https://www.npmjs.com/package/@agentpassport/core)

---

## The Problem

When Agent A delegates work to Agent B, how do you prove:
- Agent B had the right to act?
- It stayed within its authorized scope?
- You can revoke that right mid-flight?

Right now you can't. Every framework just trusts. agentpassport proves it.

## Demo

```bash
git clone https://github.com/ceavinrufus/agentpassport
cd agentpassport
uv run python -m demo.run_demo
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  agentpassport DEMO — Cross-SDK Trust Chain
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Orchestrator  did:key:z6MkskpV…pks2  (Python)
  TS Agent      did:key:z6MkoFDL…3TZf  (TypeScript)

[STEP 1] Python signs delegation JWT
  scope  ['read:db:customers']  ttl 3600s

[STEP 2] Python → TS: queryCustomers → 200 ✅
  Auth chain verified, capability executed

[STEP 3] Python → TS: writeCustomer → 403 🛡️
  ScopeError: requires [write:db:customers], granted [read:db:customers]

[STEP 4] Python revokes delegation mid-scenario
  jti revoked → same request fails → 403 🛡️

[STEP 5] Auth chain trace
  hop 0  jti=d77dd09a…  ✅
    iss  z6MkskpV…  (orchestrator)
    sub  z6MkoFDL…  (ts-agent)
    scope  ['read:db:customers']
    exp  2026-05-12T10:22:48Z
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## How It Works

### 1. Cryptographic Identity

Every agent has an Ed25519 keypair. Its public key becomes a W3C-standard `did:key:` DID — no central registry, verifiable by anyone.

```python
from agentpassport import Agent

agent = Agent("my-agent")
print(agent.did)  # did:key:z6Mk...
```

### 2. Signed Delegation (Auth Chain)

Trust flows through a chain of signed JWTs. Each hop narrows scope — an agent can never grant more than it has.

```python
from agentpassport import sign_delegation, verify_auth_chain

# Root signs initial grant
token = sign_delegation(
    issuer_private_key=root_priv,
    issuer_did=root_did,
    subject_did=agent.did,
    scope=["read:db:customers"],
    ttl_seconds=3600,
)

# Receiving agent verifies before acting
verify_auth_chain(
    auth_chain=[token],
    expected_subject=agent.did,
    known_public_keys={root_did: root_pub},
)
```

### 3. Pre-execution Scope Declaration

Capabilities declare what scope they need. agentpassport checks before the handler runs — fail fast, no partial state.

```python
@agent.capability("query_customers", requires=["read:db:customers"])
async def handle(task: TaskEnvelope) -> dict:
    # Only reached if auth chain grants read:db:customers
    return {"customers": [...]}
```

### 4. Revocation

Revoke a delegation by JTI without stopping in-flight work — the agent completes its current action and stops before the next.

```python
from agentpassport import InMemoryRevocationRegistry, SqliteRevocationRegistry

registry = SqliteRevocationRegistry("revocations.db")
registry.revoke(jti)  # all future requests with this token fail
```

## TypeScript SDK

Wire-compatible with Python — cross-language trust chains work out of the box.

```typescript
import { Agent, InMemoryRevocationRegistry, ScopeError } from "@agentpassport/core"

const agent = new Agent("ts-agent", { privateKey, revocationRegistry })
agent.trustKeys({ [orchestratorDid]: orchestratorPublicKey })

agent.capability("queryCustomers", { requires: ["read:db:customers"] }, async (task) => {
  return { customers: [...] }
})
```

A Python orchestrator can sign a delegation JWT. A TypeScript agent can verify it. No shared infrastructure needed.

## Scope Format

Scopes are `action:resource` pairs:

```
["read:db:customers", "write:api:stripe", "send:email:notifications"]
```

Both parts together make authorization provable. Action-only (`"read"`) is too loose. Resource-only (`"db:customers"`) is incomplete.

## Install

```bash
pip install agentpassport          # Python SDK
pip install agentpassport[otel]    # + OpenTelemetry sink
```

```bash
cd packages/agentpassport-ts && npm install  # TypeScript SDK
```

## Packages

| Package | Description |
|---------|-------------|
| `agentpassport` | Python trust and authorization layer |
| `@agentpassport/core` | TypeScript SDK (wire-compatible) |
| `agentpassport-registry` | Trusted agent registry with signature verification |
| `agentpassport-adapters` | MCP, REST, and A2A adapters |
| `agentpassport-cli` | CLI — keygen, trace viewer |

## CLI

```bash
# Generate a keypair and DID
agentpass identity keygen --alias myagent

# Inspect an auth chain from a trace
agentpass trace show --id trace_abc --file traces.jsonl
```

## Roadmap

| | Feature | Status |
|---|---|---|
| **Authorization layer** | Cryptographic agent identity (`did:key:`) | ✅ Done |
| | Signed delegation chain (JWT) | ✅ Done |
| | Scope enforcement + revocation | ✅ Done |
| | Python SDK | ✅ Done |
| | TypeScript SDK | ✅ Done |
| | Cross-language wire compatibility | ✅ Done |
| | MCP middleware adapter | ✅ Done |
| | A2A protocol adapter (inbound + outbound) | ✅ Done |
| **AI Passport** | Identity revocation | ✅ Done |
| | Ownership binding (domain → agent DID) | 🔜 Next |
| | Decentralized agent discovery | 🔜 Planned |
| | Human-readable ownership declaration | 🔜 Planned |

## Development

```bash
uv sync --all-packages
uv run pytest                          # Python tests (173)
cd packages/agentpassport-ts && npm test     # TypeScript tests (48)
uv run python -m tests.cross-sdk.generate_fixtures && \
  cd tests/cross-sdk && npx tsx generate_ts_fixtures.ts  # cross-SDK fixtures
```

## License

MIT
