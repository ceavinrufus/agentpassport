# agentpassport

[![PyPI](https://img.shields.io/pypi/v/agentpassport)](https://pypi.org/project/agentpassport/)
[![npm](https://img.shields.io/npm/v/@agentpassport/core)](https://www.npmjs.com/package/@agentpassport/core)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/ceavinrufus/agentpassport/actions/workflows/ci.yml/badge.svg)](https://github.com/ceavinrufus/agentpassport/actions/workflows/ci.yml)

**The AI passport layer.**

> Cryptographic delegation for AI agents. Prove what an agent was authorized to do — across languages, frameworks, and trust boundaries.

Agents are flooding the internet. They're sending emails, making purchases, running code — on your behalf, or someone else's. But there's no standard way to prove who an agent belongs to, what it's authorized to do, or whether it stayed within bounds.

agentpassport is building that. Starting with the authorization primitive — cryptographic proof of delegation at every hop. Growing into full agent identity and ownership verification across the open web.

**Today:** prove an agent was authorized to act.
**Next:** prove who it belongs to.

```
[Python Orchestrator] signs delegation → [TypeScript Agent] verifies before executing
         ↓
    ScopeError: requires [write:db:customers], granted [read:db:customers]  ✅
```

## Why agentpassport?

| | Without agentpassport | With agentpassport |
|---|---|---|
| Agent authorization | Trust by convention | Cryptographic proof |
| Scope enforcement | Ad-hoc checks | Declared + verified before execution |
| Revocation | Kill the process | Soft-stop by JTI, mid-flight safe |
| Cross-language | Custom per integration | Wire-compatible out of the box |

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

**Cross-SDK trust chain** — Python orchestrator delegates to TypeScript agent:

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

**Ownership binding** — domain + wallet binding, offline verification, revocation:

```bash
uv run python -m demo.binding_demo
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  agentpassport — Ownership Binding Demo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[STEP 1] Generate agent identity
  DID:               did:key:z6Mkv4kj…
  ✅  Agent identity created

[STEP 2] Bind agent to domain 'rufus.dev'
  ✅  Domain binding created

[STEP 3] Bind agent to Ethereum wallet
  ✅  Wallet binding created

[STEP 4] Assemble binding document
  Document (publish at https://rufus.dev/.well-known/agent-passport.json)

[STEP 5] Verify signatures offline
  ✅  Domain binding signature valid
  ✅  Wallet binding signature valid
  ✅  Tampered signature correctly rejected
  ✅  Expired binding correctly rejected

[STEP 6] Revoke wallet binding
  ✅  Wallet binding is now revoked
  ✅  Domain binding unaffected by wallet revocation

[STEP 7] Final document state
  binding  type=domain [active]
  binding  type=wallet [REVOKED]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
| [`agentpassport`](https://pypi.org/project/agentpassport/) [![PyPI](https://img.shields.io/pypi/v/agentpassport)](https://pypi.org/project/agentpassport/) | Python trust and authorization layer |
| [`@agentpassport/core`](https://www.npmjs.com/package/@agentpassport/core) [![npm](https://img.shields.io/npm/v/@agentpassport/core)](https://www.npmjs.com/package/@agentpassport/core) | TypeScript SDK (wire-compatible) |
| [`agentpassport-registry`](https://pypi.org/project/agentpassport-registry/) [![PyPI](https://img.shields.io/pypi/v/agentpassport-registry)](https://pypi.org/project/agentpassport-registry/) | Trusted agent registry with signature verification |
| [`agentpassport-adapters`](https://pypi.org/project/agentpassport-adapters/) [![PyPI](https://img.shields.io/pypi/v/agentpassport-adapters)](https://pypi.org/project/agentpassport-adapters/) | MCP, REST, and A2A adapters |
| [`agentpassport-cli`](https://pypi.org/project/agentpassport-cli/) [![PyPI](https://img.shields.io/pypi/v/agentpassport-cli)](https://pypi.org/project/agentpassport-cli/) | CLI — keygen, trace viewer |

## CLI

```bash
# Generate a keypair and DID
agentpass identity keygen --alias myagent

# Inspect an auth chain from a trace
agentpass trace show --id trace_abc --file traces.jsonl
```

## Ownership Binding

Agents can prove real-world ownership by publishing a signed binding document at `/.well-known/agent-passport.json`.

```python
from agentpassport import (
    generate_keypair, did_from_public_key,
    bind_domain, bind_wallet, BindingDocument,
    verify_binding_attestation,
)

priv, pub = generate_keypair()
did = did_from_public_key(pub)

# Create bindings
domain_binding = bind_domain(priv[:32], did, "rufus.dev")
wallet_binding = bind_wallet(priv[:32], did, "ethereum", "0xYourAddress")

# Assemble and publish
doc = BindingDocument(version="1")
doc.add(domain_binding)
doc.add(wallet_binding)
print(doc.to_json())  # publish at https://rufus.dev/.well-known/agent-passport.json

# Verify offline
ok = verify_binding_attestation(domain_binding)  # True
```

Or use the CLI:

```bash
agentpass identity bind-domain --alias myagent --domain rufus.dev --output ap.json
agentpass identity bind-wallet --alias myagent --chain ethereum --address 0x... --output ap.json
agentpass identity verify-domain --did <DID> --domain rufus.dev
```

See the [Ownership Binding guide](docs/guides/ownership-binding.md) for the full flow.

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
| | Domain ownership binding | ✅ Done |
| | Wallet ownership binding (chain-agnostic) | ✅ Done |
| | Decentralized agent discovery | 🔜 Planned |
| | Merkle tree revocation (scalable, on-chain ready) | 🔜 Planned |
| | Human-readable ownership declaration | 🔜 Planned |

## Development

```bash
uv sync --all-packages
uv run pytest                          # Python tests (173)
cd packages/agentpassport-ts && npm test     # TypeScript tests (48)
uv run python -m tests.cross-sdk.generate_fixtures && \
  cd tests/cross-sdk && npx tsx generate_ts_fixtures.ts  # cross-SDK fixtures
```

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache-2.0
