# Guide: Cross-SDK Interoperability

agentpassport's Python and TypeScript SDKs are **wire-compatible**: a token signed by Python verifies in TypeScript, and vice versa. This guide explains how that works, demonstrates both directions with complete runnable code, and covers the edge cases.

---

## Table of Contents

1. [Why wire compatibility matters](#1-why-wire-compatibility-matters)
2. [What "wire-compatible" means exactly](#2-what-wire-compatible-means-exactly)
3. [Key layout compatibility](#3-key-layout-compatibility)
4. [Python signs → TypeScript verifies](#4-python-signs--typescript-verifies)
5. [TypeScript signs → Python verifies](#5-typescript-signs--python-verifies)
6. [Three-hop chain across languages](#6-three-hop-chain-across-languages)
7. [Sharing public keys between SDKs](#7-sharing-public-keys-between-sdks)
8. [Running the cross-SDK test suite](#8-running-the-cross-sdk-test-suite)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Why wire compatibility matters

Real multi-agent systems aren't monoglot. Your orchestrator might be Python (LangGraph, CrewAI), your tool-calling agents TypeScript (Vercel AI SDK, LangChain.js), and tomorrow something else. agentpassport's trust chain needs to work across all of them without a translation layer.

---

## 2. What "wire-compatible" means exactly

Both SDKs produce and consume the same compact JWT format:

```
<base64url(header)>.<base64url(payload)>.<base64url(signature)>
```

**Header** — identical in both:
```json
{"alg":"EdDSA","crv":"Ed25519"}
```

**Payload** — sorted keys (alphabetical), no extra whitespace:
```json
{"exp":1717127056,"iss":"did:key:z6Mk...","iat":1717123456,"jti":"uuid4","max_delegations":0,"scope":["read:db"],"sub":"did:key:z6Mk..."}
```

The key detail: **both SDKs sort JSON keys alphabetically before encoding**. Python uses `json.dumps(..., sort_keys=True)`. TypeScript uses `Object.keys().sort()`. This produces byte-for-byte identical payloads for the same claims, which means signatures created in one SDK verify in the other.

**Signature** — Ed25519 over `UTF-8("<header>.<payload>")`, base64url-encoded, no padding.

**DID format** — both use `did:key:z<base58btc(0xed01 + public_key_bytes)>` with the same alphabet and the same multicodec prefix `0xed 0x01`.

---

## 3. Key layout compatibility

Both SDKs use the same 64-byte private key layout:

```
private_key[0:32]  = Ed25519 seed (the actual signing scalar input)
private_key[32:64] = Ed25519 public key bytes
```

When you sign, only the first 32 bytes (the seed) are used. This matches PyNaCl's `SigningKey` convention and `@noble/ed25519`'s `sign(message, seed)` API.

To share a keypair between SDKs, serialize as hex and pass across:

```
Python private key (bytes) → .hex() → JSON/env → TypeScript Uint8Array (fromHex)
Python public key  (bytes) → .hex() → JSON/env → TypeScript Uint8Array (fromHex)
```

---

## 4. Python signs → TypeScript verifies

### Setup

```bash
# Python side
pip install agentpassport

# TypeScript side  
npm install @agentpassport/core
```

### Step 1: Python creates a keypair and signs a delegation

```python
# py_signer.py
import json
from agentpassport import generate_keypair, did_from_public_key, sign_delegation

# Generate identity
private_key, public_key = generate_keypair()
issuer_did = did_from_public_key(public_key)

# Who we're delegating to (TypeScript agent)
# In real use, this DID comes from the TS agent's Agent.did property
subject_did = "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"

# Sign a delegation JWT
token = sign_delegation(
    issuer_private_key=private_key,
    issuer_did=issuer_did,
    subject_did=subject_did,
    scope=["read:db:customers", "read:cache"],
    ttl_seconds=3600,
    max_delegations=2,
)

# Export what the TypeScript side needs to verify
fixture = {
    "token": token,
    "issuer_did": issuer_did,
    "issuer_public_key_hex": public_key.hex(),
    "subject_did": subject_did,
}

print(json.dumps(fixture, indent=2))
# Save to a file or pass via env/HTTP
with open("py_fixture.json", "w") as f:
    json.dump(fixture, f)
```

### Step 2: TypeScript receives the token and verifies

```typescript
// ts_verifier.ts
import { readFileSync } from "fs";
import { verifyAuthChain } from "agentpassport";

const fixture = JSON.parse(readFileSync("py_fixture.json", "utf-8"));

// Convert hex public key back to Uint8Array
function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

const knownPublicKeys = new Map<string, Uint8Array>([
  [fixture.issuer_did, fromHex(fixture.issuer_public_key_hex)],
]);

const result = verifyAuthChain({
  chain: [fixture.token],
  expectedSubject: fixture.subject_did,
  knownPublicKeys,
});

console.log("Verified:", result); // Verified: true

// You can also decode the claims for inspection:
import { decodeJwtClaims } from "agentpassport";
const claims = decodeJwtClaims(fixture.token);
console.log("Claims:", claims);
// {
//   iss: "did:key:z6Mk...",
//   sub: "did:key:z6Mk...",
//   iat: 1717123456,
//   exp: 1717127056,
//   jti: "550e8400-...",
//   scope: ["read:db:customers", "read:cache"],
//   max_delegations: 2
// }
```

### Step 3: TypeScript Agent uses the token to gate a capability

```typescript
// ts_agent.ts
import { Agent, createTask } from "agentpassport";
import { readFileSync } from "fs";

const fixture = JSON.parse(readFileSync("py_fixture.json", "utf-8"));

function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

// Create agent with the subject DID's private key
// (In real use, the TS agent has its own keypair and its DID matches subject_did)
const agent = new Agent("ts-worker");

// Trust the Python orchestrator
agent.trustKeys({
  [fixture.issuer_did]: fromHex(fixture.issuer_public_key_hex),
});

// Register a scoped capability
agent.capability(
  "queryCustomers",
  { requires: ["read:db:customers"] },
  async (task) => {
    return { rows: [{ id: 1, name: "Alice" }] };
  }
);

// Build a task that carries the Python-signed auth chain
const task = createTask(
  { type: "queryCustomers", params: { limit: 10 } },
  {
    auth_chain: [fixture.token],
    // The subject_did in the token must match agent.did for verification to pass.
    // In a real integration, generate the TS agent's keypair first, get its DID,
    // then pass that DID to Python when generating the fixture.
  }
);

// Handle the task — TrustMiddleware checks scope before handler runs
try {
  const result = await agent.handle(task);
  console.log("Result:", result); // { rows: [{ id: 1, name: "Alice" }] }
} catch (e) {
  console.error("Rejected:", e.message);
}
```

---

## 5. TypeScript signs → Python verifies

### Step 1: TypeScript creates a keypair and signs

```typescript
// ts_signer.ts
import { writeFileSync } from "fs";
import { generateKeypair, didFromPublicKey, signDelegation } from "agentpassport";

// Generate identity
const kp = generateKeypair();
const issuerDid = didFromPublicKey(kp.publicKey);

// Python agent's DID (get this from the Python side first)
const subjectDid = "did:key:z6Mktpk7e8FdmVPgBhbL3xJp5Fg4XxnAhWnNEGZPwYCd1aV";

// Sign
const token = signDelegation({
  issuerPrivateKey: kp.privateKey,
  issuerDid,
  subjectDid,
  scope: ["write:cache", "read:db"],
  ttlSeconds: 3600,
  maxDelegations: 1,
});

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
}

const fixture = {
  token,
  issuer_did: issuerDid,
  issuer_public_key_hex: toHex(kp.publicKey),
  subject_did: subjectDid,
};

writeFileSync("ts_fixture.json", JSON.stringify(fixture, null, 2));
console.log("Fixture written to ts_fixture.json");
console.log("Issuer DID:", issuerDid);
```

### Step 2: Python receives and verifies

```python
# py_verifier.py
import json
from agentpassport.identity.signing import verify_auth_chain

with open("ts_fixture.json") as f:
    fixture = json.load(f)

known_keys = {
    fixture["issuer_did"]: bytes.fromhex(fixture["issuer_public_key_hex"])
}

result = verify_auth_chain(
    auth_chain=[fixture["token"]],
    expected_subject=fixture["subject_did"],
    known_public_keys=known_keys,
)

print("Verified:", result)  # Verified: True
```

### Step 3: Python Agent uses the token

```python
# py_agent.py
import asyncio
import json
from agentpassport import Agent, TaskEnvelope, Intent, Constraints

with open("ts_fixture.json") as f:
    fixture = json.load(f)

# Create agent — in real use, load the keypair that matches subject_did
agent = Agent("py-worker")

# Trust the TypeScript orchestrator
agent.trust_keys({
    fixture["issuer_did"]: bytes.fromhex(fixture["issuer_public_key_hex"])
})

@agent.capability("writeCache", requires=["write:cache"])
async def write_cache(task: TaskEnvelope) -> dict:
    key = task.intent.params.get("key")
    value = task.intent.params.get("value")
    return {"written": True, "key": key}


async def main():
    task = TaskEnvelope(
        intent=Intent(type="writeCache", params={"key": "session:123", "value": "data"}),
        constraints=Constraints(budget_credits=10, max_delegations=5,
                                allowed_capabilities=[], denied_capabilities=[]),
        auth_chain=[fixture["token"]],
    )

    try:
        result = await agent.handle(task)
        print("Result:", result)  # Result: {'written': True, 'key': 'session:123'}
    except Exception as e:
        print("Rejected:", e)


asyncio.run(main())
```

---

## 6. Three-hop chain across languages

A real deployment might have: Python orchestrator → TypeScript gateway → Python worker.

```
Python orchestrator  ──JWT1──▶  TypeScript gateway  ──JWT1+JWT2──▶  Python worker
  iss=orchestrator.did            iss=gateway.did                     verifies JWT1+JWT2
  sub=gateway.did                 sub=worker.did                      checks scope
  scope=["read:db","write:cache"] scope=["read:db"]                   runs handler
```

### Python orchestrator (step 1: create chain)

```python
# orchestrator.py
import asyncio
from agentpassport import Agent, TaskEnvelope, Intent, Constraints

orchestrator = Agent("orchestrator")

# Export orchestrator's public key for the other agents to trust
print("Orchestrator DID:", orchestrator.did)
print("Orchestrator pubkey:", orchestrator.public_key.hex())
```

### TypeScript gateway (step 2: verify + extend chain)

```typescript
// gateway.ts
import { Agent, createTask } from "agentpassport";

const ORCHESTRATOR_DID = process.env.ORCHESTRATOR_DID!;
const ORCHESTRATOR_PUBKEY = process.env.ORCHESTRATOR_PUBKEY!;
const WORKER_DID = process.env.WORKER_DID!;

function fromHex(hex: string): Uint8Array {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) b[i/2] = parseInt(hex.slice(i, i+2), 16);
  return b;
}

const gateway = new Agent("ts-gateway");

// Trust the Python orchestrator
gateway.trustKeys({
  [ORCHESTRATOR_DID]: fromHex(ORCHESTRATOR_PUBKEY),
});

// The gateway has a capability that:
// 1. Verifies the incoming chain from the orchestrator
// 2. Creates a new delegation to the Python worker (narrowing scope)
// 3. Returns the extended chain for forwarding

gateway.capability(
  "forwardQuery",
  { requires: ["read:db"] },   // Must be granted by orchestrator
  async (task) => {
    // Extend the chain — gateway delegates to Python worker
    const extendedTask = gateway.delegate(task, {
      targetDid: WORKER_DID,
      scope: ["read:db"],       // narrowed — no write:cache
      ttlSeconds: 300,
    });

    // Return the extended auth_chain for the Python worker
    return { auth_chain: extendedTask.auth_chain };
  }
);
```

### Python worker (step 3: verify full chain)

```python
# worker.py
import asyncio
import os
from agentpassport import Agent, TaskEnvelope, Intent, Constraints

ORCHESTRATOR_DID = os.environ["ORCHESTRATOR_DID"]
ORCHESTRATOR_PUBKEY = bytes.fromhex(os.environ["ORCHESTRATOR_PUBKEY"])
GATEWAY_DID = os.environ["GATEWAY_DID"]
GATEWAY_PUBKEY = bytes.fromhex(os.environ["GATEWAY_PUBKEY"])

worker = Agent("py-worker")

# Trust both upstream agents
worker.trust_keys({
    ORCHESTRATOR_DID: ORCHESTRATOR_PUBKEY,
    GATEWAY_DID: GATEWAY_PUBKEY,
})

@worker.capability("queryDB", requires=["read:db"])
async def query_db(task: TaskEnvelope) -> dict:
    # auth_chain contains [JWT_orchestrator→gateway, JWT_gateway→worker]
    # TrustMiddleware verified both before this handler ran
    return {"rows": [{"id": 1, "name": "Alice"}]}
```

### Why this works

`verify_auth_chain` checks every token in order. `TrustMiddleware.check()` collects scopes from tokens whose `sub` matches the agent's own DID — in the worker's case, only `JWT_gateway→worker`. The scope `read:db` appears there, so the check passes.

---

## 7. Sharing public keys between SDKs

The only thing one SDK needs from another to verify tokens is the **issuer's public key as raw bytes (hex-encoded for transport)**. There is no certificate, no CA, no X.509.

### Options for sharing public keys

**Option A: Environment variables (simple deployments)**

```python
# generate_and_export.py
from agentpassport import generate_keypair, did_from_public_key

private_key, public_key = generate_keypair()
print("DID:", did_from_public_key(public_key))
print("PUBLIC_KEY_HEX:", public_key.hex())
# Save private_key securely (not in env!)
```

```bash
export ORCHESTRATOR_DID="did:key:z6Mk..."
export ORCHESTRATOR_PUBKEY_HEX="abc123..."
```

**Option B: AgentCard (structured identity document)**

The `AgentCard` type is designed exactly for this — it carries the agent's DID, capabilities, endpoint, and a signed identity claim. Agents can fetch each other's AgentCards from a registry or well-known URL.

```python
from agentpassport import Agent, AgentCard, sign_agent_card, parse_did, generate_keypair

# Store the private key when creating the agent so you can sign cards
priv, pub = generate_keypair()
agent = Agent("orchestrator", private_key=priv)

# Construct AgentCard manually
card = AgentCard(
    did=agent.did,
    name=agent.name,
    capabilities=["run"],
    endpoint="http://localhost:8000",
)
signed_card = sign_agent_card(card, priv)  # priv is the 64-byte keypair bytes

# Publish as JSON
card_json = signed_card.model_dump_json()

# Any SDK can extract the public key from the DID
pub_key_bytes = parse_did(signed_card.did)
```

**Option C: Out-of-band (hardcoded in config)**

For static deployments, just hardcode the hex public keys in your config file. It's a static 64-character hex string — it never changes unless you rotate keys.

---

## 8. Running the cross-SDK test suite

The repo ships with a cross-SDK test suite in `tests/cross-sdk/`. It covers:
- Python signs single-hop JWT → TypeScript verifies
- TypeScript signs single-hop JWT → Python verifies
- TypeScript builds 3-hop chain → Python verifies full chain
- Python builds 3-hop chain → TypeScript verifies full chain
- Tampered tokens are rejected by both SDKs
- Wrong expected subject is rejected by both SDKs

### Run the Python-verifies-TS tests

```bash
# From repo root
# Step 1: Generate TypeScript fixtures
cd packages/agentpassport-ts
npx tsx tests/generate_ts_fixtures.ts
# Writes tests/cross-sdk/ts_fixtures.json

# Step 2: Run Python verification tests
cd ../../
uv run pytest tests/cross-sdk/test_cross_sdk.py -v
```

Expected output:
```
tests/cross-sdk/test_cross_sdk.py::test_ts_single_hop_verified_by_python PASSED
tests/cross-sdk/test_cross_sdk.py::test_ts_three_hop_chain_verified_by_python PASSED
tests/cross-sdk/test_cross_sdk.py::test_ts_three_hop_wrong_subject_rejected_by_python PASSED
tests/cross-sdk/test_cross_sdk.py::test_tampered_ts_jwt_rejected_by_python PASSED
```

### Run the TS-verifies-Python tests

```bash
cd packages/agentpassport-ts
npx vitest run
```

---

## 9. Troubleshooting

### "Invalid JWT signature" when verifying cross-SDK

**Cause 1: Wrong public key passed.**
Double-check that the public key hex you're passing to `knownPublicKeys` corresponds to the issuer DID in the token's `iss` claim. The DID is derived from the public key — use `parseDid(did)` (TS) or `parse_did(did)` (Python) to extract the public key bytes and compare.

```python
# Python: extract public key from DID and compare
from agentpassport import parse_did
pub_from_did = parse_did(issuer_did)
assert pub_from_did == your_public_key_bytes, "Key mismatch!"
```

**Cause 2: Passing the full 64-byte private key instead of the 32-byte public key.**
`public_key` is 32 bytes. `private_key` is 64 bytes. Don't confuse them.

**Cause 3: JSON key sort mismatch.**
If you're hand-crafting JWTs or wrapping the SDKs, ensure the payload JSON has keys sorted alphabetically. Any deviation breaks the signature.

### Token verifies in Python but fails in TypeScript (or vice versa)

Check the `iat`/`exp` timestamps. Python uses `datetime.now(timezone.utc).timestamp()` and TypeScript uses `Date.now() / 1000`. If there's clock skew between machines, tokens can appear expired on one side.

### `verify_auth_chain` returns `False` but I'm sure the token is valid

Use `decodeJwtClaims()` / `_decode_jwt_claims()` to inspect the token without verification and check:
1. Is `iss` a key in your `known_public_keys` / `knownPublicKeys`?
2. Is `sub` what you're passing as `expected_subject`?
3. Is `exp` in the future? (Unix timestamp, seconds)
4. Is `jti` present and non-empty?
