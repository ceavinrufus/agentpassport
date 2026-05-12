# aps-sdk-ts — TypeScript SDK

Wire-compatible TypeScript SDK for APS. Same four primitives as the Python SDK — cross-language trust chains work out of the box.

## Install

```bash
npm install
```

## Quickstart

```typescript
import { Agent, InMemoryRevocationRegistry, ScopeError } from "@aps/sdk-ts"

const revocationRegistry = new InMemoryRevocationRegistry()
const agent = new Agent("ts-agent", { privateKey, revocationRegistry })

// Trust a Python orchestrator
agent.trustKeys({ [orchestratorDid]: orchestratorPublicKey })

// Declare required scope
agent.capability("queryCustomers", { requires: ["read:db:customers"] }, async (task) => {
  return { customers: [...] }
})

// Handle incoming task (verifies auth chain automatically)
const result = await agent.handle(task)
```

## Primitives

- **Identity** — Ed25519 keypair → `did:key:z<base58btc>` DID (same format as Python)
- **Auth chain** — sign/verify EdDSA JWTs, `verifyAuthChain()` mirrors Python exactly
- **TrustMiddleware** — scope declaration + enforcement, `ScopeError` on violation
- **RevocationRegistry** — `InMemoryRevocationRegistry` interface

## Wire Compatibility

JWT format is identical to the Python SDK:
- Header: `{"alg":"EdDSA","crv":"Ed25519"}`
- Claims sorted alphabetically (matches Python's `sort_keys=True`)
- `did:key:z<base58btc>` with `0xed01` multicodec prefix

A Python orchestrator can sign a delegation JWT. A TypeScript agent can verify it independently.

## Development

```bash
npm install
npm test
```
