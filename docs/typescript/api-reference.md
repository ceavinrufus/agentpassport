# AgentPassport TypeScript SDK — API Reference

Complete reference for every exported symbol from the `@agentpassport/core` package. For conceptual background see `docs/concepts.md`.

---

## Table of Contents

- [Installation](#installation)
- [Module overview](#module-overview)
- [Identity](#identity)
  - [Interface: `Keypair`](#interface-keypair)
  - [`generateKeypair()`](#generatekeypair)
  - [`keypairFromSeed()`](#keypairfromseed)
  - [`didFromPublicKey()`](#didfrompublickey)
  - [`parseDid()`](#parsedid)
  - [`base58btcEncode()`](#base58btcencode)
  - [`base58btcDecode()`](#base58btcdecode)
- [JWT](#jwt)
  - [Interface: `DelegationClaims`](#interface-delegationclaims)
  - [Interface: `SignDelegationOptions`](#interface-signdelegationoptions)
  - [Interface: `VerifyAuthChainOptions`](#interface-verifyauthchainoptions)
  - [`signDelegation()`](#signdelegation)
  - [`verifyAuthChain()`](#verifyauthchain)
  - [`decodeJwtClaims()`](#decodejwtclaims)
- [Revocation](#revocation)
  - [Interface: `RevocationRegistry`](#interface-revocationregistry)
  - [Class: `InMemoryRevocationRegistry`](#class-inmemoryrevocationregistry)
- [Trust](#trust)
  - [Class: `ScopeError`](#class-scopeerror)
  - [Class: `TrustMiddleware`](#class-trustmiddleware)
- [Agent](#agent)
  - [Type: `CapabilityHandler`](#type-capabilityhandler)
  - [Interface: `CapabilityOptions`](#interface-capabilityoptions)
  - [Interface: `DelegateOptions`](#interface-delegateoptions)
  - [Class: `Agent`](#class-agent)
- [Types](#types)
  - [Type: `TaskState`](#type-taskstate)
  - [Interface: `Intent`](#interface-intent)
  - [Interface: `Constraints`](#interface-constraints)
  - [Interface: `TaskEnvelope`](#interface-taskenvelope)
  - [`createTask()`](#createtask)
- [Internal helpers](#internal-helpers)

---

## Installation

```bash
npm install @agentpassport/core
# or
yarn add @agentpassport/core
# or
pnpm add @agentpassport/core
```

**Requirements:** Node.js 18+ (uses `crypto.randomUUID()`, `atob`, `btoa`). Browser-compatible with modern bundlers.

**Dependencies:** `@noble/ed25519`, `@noble/hashes`.

---

## Module overview

```typescript
import {
  // identity
  generateKeypair,
  keypairFromSeed,
  didFromPublicKey,
  parseDid,
  base58btcEncode,
  base58btcDecode,
  type Keypair,

  // jwt
  signDelegation,
  verifyAuthChain,
  decodeJwtClaims,
  type DelegationClaims,
  type SignDelegationOptions,
  type VerifyAuthChainOptions,

  // revocation
  InMemoryRevocationRegistry,
  type RevocationRegistry,

  // trust
  TrustMiddleware,
  ScopeError,

  // agent
  Agent,
  type CapabilityHandler,
  type CapabilityOptions,
  type DelegateOptions,

  // types
  createTask,
  type TaskEnvelope,
  type TaskState,
  type Intent,
  type Constraints,
} from "@agentpassport/core";
```

---

## Identity

All identity functions live in `src/identity.ts`.

### Interface: `Keypair`

```typescript
interface Keypair {
  /** 64-byte Uint8Array: first 32 bytes = Ed25519 seed, last 32 bytes = public key */
  privateKey: Uint8Array;
  /** 32-byte Ed25519 public key */
  publicKey: Uint8Array;
}
```

This layout mirrors the Python SDK (`bytes(sk) + bytes(sk.verify_key)`) for cross-SDK wire compatibility. When signing, only the first 32 bytes (the seed) are passed to the Ed25519 sign function.

---

### `generateKeypair()`

```typescript
function generateKeypair(): Keypair
```

Generate a new random Ed25519 keypair using `@noble/ed25519` and OS-provided randomness.

**Parameters:** None

**Returns:** `Keypair` — `{ privateKey: Uint8Array(64), publicKey: Uint8Array(32) }`

**Throws:** Nothing. Uses `ed.utils.randomPrivateKey()` which relies on the platform's CSPRNG.

**Example 1: Generate and inspect**
```typescript
import { generateKeypair } from "@agentpassport/core";

const kp = generateKeypair();
console.log(kp.privateKey.length); // 64
console.log(kp.publicKey.length);  // 32
```

**Example 2: Use with Agent**
```typescript
import { generateKeypair, Agent } from "@agentpassport/core";

const kp = generateKeypair();
const agent = new Agent("my-agent", { privateKey: kp.privateKey });
console.log(agent.did); // did:key:z6Mk...
```

**Example 3: Persist and restore**
```typescript
import { generateKeypair, keypairFromSeed } from "@agentpassport/core";
import { writeFileSync, readFileSync } from "fs";

const kp = generateKeypair();
const seed = kp.privateKey.slice(0, 32);

// Persist the 32-byte seed
writeFileSync("agent.seed", seed);

// Restore
const restoredSeed = readFileSync("agent.seed");
const restoredKp = keypairFromSeed(new Uint8Array(restoredSeed));
console.log(restoredKp.publicKey); // identical to original kp.publicKey
```

---

### `keypairFromSeed()`

```typescript
function keypairFromSeed(seed: Uint8Array): Keypair
```

Build a `Keypair` from a raw 32-byte Ed25519 seed. Useful for deterministic key derivation or restoring from a persisted seed.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `seed` | `Uint8Array` | Yes | Exactly 32 bytes. The Ed25519 private scalar seed. |

**Returns:** `Keypair` — deterministically derived from the seed.

**Throws:** `Error` — if `seed.length !== 32`.

**Example 1: Deterministic keypair from a fixed seed**
```typescript
import { keypairFromSeed, didFromPublicKey } from "@agentpassport/core";

const seed = new Uint8Array(32).fill(0x42); // 32 bytes of 0x42
const kp = keypairFromSeed(seed);

// Same seed always gives same DID
const did = didFromPublicKey(kp.publicKey);
console.log(did); // always the same string
```

**Example 2: Error on wrong seed length**
```typescript
try {
  keypairFromSeed(new Uint8Array(16)); // wrong length
} catch (e) {
  console.log(e.message); // "Seed must be 32 bytes"
}
```

---

### `didFromPublicKey()`

```typescript
function didFromPublicKey(publicKey: Uint8Array): string
```

Encode a 32-byte Ed25519 public key as a `did:key:z...` DID string.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `publicKey` | `Uint8Array` | Yes | 32-byte Ed25519 verify key. |

**Returns:** `string` — DID string, e.g. `"did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"`.

**Throws:** Nothing. Encoding is always successful for valid byte inputs.

**Algorithm:**
1. Prepend `[0xed, 0x01]` (Ed25519 multicodec prefix) to the 32-byte key.
2. Base58btc-encode the 34-byte result.
3. Return `"did:key:z" + encoded`.

**Example 1: Basic usage**
```typescript
import { generateKeypair, didFromPublicKey } from "@agentpassport/core";

const { publicKey } = generateKeypair();
const did = didFromPublicKey(publicKey);
console.log(did); // did:key:z6Mk...
```

**Example 2: Determinism**
```typescript
const { publicKey } = generateKeypair();
const did1 = didFromPublicKey(publicKey);
const did2 = didFromPublicKey(publicKey);
console.log(did1 === did2); // true
```

**Example 3: Wire compatibility with Python SDK**
```python
# Python
from agentpassport import generate_keypair, did_from_public_key
priv, pub = generate_keypair()
did = did_from_public_key(pub)
# Pass pub bytes and did to TypeScript tests — they will match
```

```typescript
// TypeScript receives pub bytes as Uint8Array
const tsDid = didFromPublicKey(pubBytesFromPython);
console.log(tsDid === didFromPython); // true
```

---

### `parseDid()`

```typescript
function parseDid(did: string): Uint8Array
```

Extract the 32-byte Ed25519 public key from a `did:key:z...` DID string.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `did` | `string` | Yes | A `did:key:z...` DID string. |

**Returns:** `Uint8Array` — 32-byte public key.

**Throws:**
- `Error` — if `did` does not start with `"did:key:z"`.
- `Error` — if decoded bytes don't begin with the Ed25519 multicodec prefix `[0xed, 0x01]`.

**Example 1: Basic usage**
```typescript
import { parseDid } from "@agentpassport/core";

const pubKey = parseDid("did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK");
console.log(pubKey.length); // 32
```

**Example 2: Error on unsupported DID method**
```typescript
try {
  parseDid("did:web:example.com");
} catch (e) {
  console.log(e.message);
  // "Invalid did:key DID (expected did:key:z...): did:web:example.com"
}
```

**Example 3: Use to derive trust key from DID alone**
```typescript
import { Agent, parseDid } from "@agentpassport/core";

const agent = new Agent("worker");
const issuerDid = "did:key:z6Mk...";
const issuerPub = parseDid(issuerDid); // no separate channel needed

agent.trustKeys({ [issuerDid]: issuerPub });
```

---

### `base58btcEncode()`

```typescript
function base58btcEncode(data: Uint8Array): string
```

Encode bytes using the base58btc alphabet (Bitcoin/IPFS/W3C standard). Pure implementation, no external dependency.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `data` | `Uint8Array` | Yes | Raw bytes to encode. |

**Returns:** `string` — base58btc-encoded string.

**Throws:** Nothing.

**Example:**
```typescript
import { base58btcEncode } from "@agentpassport/core";

const bytes = new Uint8Array([0xed, 0x01, ...publicKeyBytes]);
const encoded = base58btcEncode(bytes);
console.log(encoded); // starts with "z" after prepending "z" for DID
```

---

### `base58btcDecode()`

```typescript
function base58btcDecode(s: string): Uint8Array
```

Decode a base58btc-encoded string back to bytes.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `s` | `string` | Yes | base58btc-encoded string. |

**Returns:** `Uint8Array` — decoded bytes.

**Throws:** `Error` — if the string contains characters not in the base58btc alphabet.

---

## JWT

All JWT functions live in `src/jwt.ts`.

### Interface: `DelegationClaims`

```typescript
interface DelegationClaims {
  iss: string;           // Issuer DID
  sub: string;           // Subject DID
  iat: number;           // Issued-at Unix timestamp (seconds)
  exp: number;           // Expiry Unix timestamp (seconds)
  jti: string;           // UUID4 unique token ID
  scope: string[];       // Permission strings
  max_delegations: number; // Remaining delegation hops
}
```

Represents the decoded payload of a delegation JWT. All fields are present in every token produced by `signDelegation()`.

---

### Interface: `SignDelegationOptions`

```typescript
interface SignDelegationOptions {
  issuerPrivateKey: Uint8Array;  // 64-byte (seed+pubkey) or 32-byte seed
  issuerDid: string;             // Issuer's DID
  subjectDid: string;            // Subject's DID
  scope: string[];               // Permissions to grant
  ttlSeconds?: number;           // Default: 3600
  maxDelegations?: number;       // Default: 0
}
```

Options object for `signDelegation()`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `issuerPrivateKey` | `Uint8Array` | Yes | — | 64-byte keypair or 32-byte seed. Only first 32 bytes used for signing. |
| `issuerDid` | `string` | Yes | — | Issuer's DID (`iss` claim) |
| `subjectDid` | `string` | Yes | — | Subject's DID (`sub` claim) |
| `scope` | `string[]` | Yes | — | Scopes to grant |
| `ttlSeconds` | `number` | No | `3600` | Token validity window in seconds |
| `maxDelegations` | `number` | No | `0` | Further delegation hops the subject may make |

---

### Interface: `VerifyAuthChainOptions`

```typescript
interface VerifyAuthChainOptions {
  chain: string[];
  expectedSubject: string;
  knownPublicKeys: Map<string, Uint8Array>;
  revocationRegistry?: RevocationRegistry;
}
```

Options object for `verifyAuthChain()`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `chain` | `string[]` | Yes | — | Array of compact JWT strings |
| `expectedSubject` | `string` | Yes | — | DID the final token's `sub` must equal |
| `knownPublicKeys` | `Map<string, Uint8Array>` | Yes | — | Issuer DID → 32-byte public key |
| `revocationRegistry` | `RevocationRegistry` | No | `undefined` | Optional revocation checker |

---

### `signDelegation()`

```typescript
function signDelegation(opts: SignDelegationOptions): string
```

Create a signed EdDSA JWT delegation token.

**Parameters:** `SignDelegationOptions` (see above).

**Returns:** `string` — compact JWT (`header.payload.signature`, base64url without padding).

**Throws:** Nothing under normal operation. `@noble/ed25519` signing is deterministic and always succeeds for valid inputs.

**JWT claims produced:**
```json
{
  "exp": <now + ttlSeconds>,
  "iss": "<issuerDid>",
  "iat": <now>,
  "jti": "<uuid4>",
  "max_delegations": <maxDelegations>,
  "scope": ["..."],
  "sub": "<subjectDid>"
}
```

**Note:** Keys are sorted alphabetically in the payload JSON — this is required for Python/TypeScript cross-SDK compatibility.

**Example 1: Basic delegation**
```typescript
import { generateKeypair, didFromPublicKey, signDelegation } from "@agentpassport/core";

const issuer = generateKeypair();
const subject = generateKeypair();
const issuerDid = didFromPublicKey(issuer.publicKey);
const subjectDid = didFromPublicKey(subject.publicKey);

const token = signDelegation({
  issuerPrivateKey: issuer.privateKey,
  issuerDid,
  subjectDid,
  scope: ["read:db:customers"],
  ttlSeconds: 3600,
});

console.log(token); // eyJ...
```

**Example 2: Short-lived wildcard token**
```typescript
const token = signDelegation({
  issuerPrivateKey: issuer.privateKey,
  issuerDid,
  subjectDid,
  scope: ["*"],
  ttlSeconds: 300, // 5 minutes
});
```

**Example 3: Token allowing further delegation**
```typescript
const token = signDelegation({
  issuerPrivateKey: issuer.privateKey,
  issuerDid,
  subjectDid,
  scope: ["read:db", "write:cache"],
  ttlSeconds: 7200,
  maxDelegations: 3,
});
```

---

### `verifyAuthChain()`

```typescript
function verifyAuthChain(opts: VerifyAuthChainOptions): boolean
```

Verify a complete chain of delegation JWTs. Returns `true` only if every token in the chain passes all checks and the last token's `sub` equals `expectedSubject`.

**Parameters:** `VerifyAuthChainOptions` (see above).

**Returns:** `boolean` — `true` if valid, `false` otherwise. Never throws; all errors are caught and return `false`.

**Verification per token:**
1. Structural validity (3 parts split by `.`)
2. `alg: "EdDSA"` in header
3. Issuer in `knownPublicKeys`
4. Valid Ed25519 signature via `@noble/ed25519`
5. `iat <= now <= exp`
6. `jti` is a non-empty string
7. `revocationRegistry?.isRevoked(jti)` returns `false`

**Final check:** `chain[last].sub === expectedSubject`

**Example 1: Single-hop chain**
```typescript
import { generateKeypair, didFromPublicKey, signDelegation, verifyAuthChain } from "@agentpassport/core";

const issuer = generateKeypair();
const subject = generateKeypair();
const issuerDid = didFromPublicKey(issuer.publicKey);
const subjectDid = didFromPublicKey(subject.publicKey);

const token = signDelegation({
  issuerPrivateKey: issuer.privateKey,
  issuerDid,
  subjectDid,
  scope: ["read:db"],
});

const ok = verifyAuthChain({
  chain: [token],
  expectedSubject: subjectDid,
  knownPublicKeys: new Map([[issuerDid, issuer.publicKey]]),
});
console.log(ok); // true
```

**Example 2: Multi-hop chain**
```typescript
const a = generateKeypair();
const b = generateKeypair();
const c = generateKeypair();
const aDid = didFromPublicKey(a.publicKey);
const bDid = didFromPublicKey(b.publicKey);
const cDid = didFromPublicKey(c.publicKey);

const jwt1 = signDelegation({
  issuerPrivateKey: a.privateKey, issuerDid: aDid, subjectDid: bDid, scope: ["*"],
});
const jwt2 = signDelegation({
  issuerPrivateKey: b.privateKey, issuerDid: bDid, subjectDid: cDid, scope: ["read:db"],
});

const ok = verifyAuthChain({
  chain: [jwt1, jwt2],
  expectedSubject: cDid,
  knownPublicKeys: new Map([
    [aDid, a.publicKey],
    [bDid, b.publicKey],
  ]),
});
console.log(ok); // true
```

**Example 3: With revocation registry**
```typescript
import { InMemoryRevocationRegistry } from "@agentpassport/core";

const registry = new InMemoryRevocationRegistry();
const token = signDelegation({ issuerPrivateKey, issuerDid, subjectDid, scope: ["*"] });

// Extract JTI
const jti = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).jti;
registry.revoke(jti);

const ok = verifyAuthChain({
  chain: [token],
  expectedSubject: subjectDid,
  knownPublicKeys: new Map([[issuerDid, issuer.publicKey]]),
  revocationRegistry: registry,
});
console.log(ok); // false
```

---

### `decodeJwtClaims()`

```typescript
function decodeJwtClaims(token: string): Record<string, unknown>
```

Decode and return the JWT payload claims **without verifying the signature**. Useful for inspection, logging, and extracting the `jti` for revocation.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `token` | `string` | Yes | A compact JWT string. |

**Returns:** `Record<string, unknown>` — the decoded payload object.

**Throws:** `Error` if the token does not have exactly 3 parts, or if the payload is not valid JSON.

**Example:**
```typescript
import { decodeJwtClaims } from "@agentpassport/core";

const claims = decodeJwtClaims(token);
console.log(claims.iss);   // "did:key:z6Mk..."
console.log(claims.sub);   // "did:key:z6Mk..."
console.log(claims.scope); // ["read:db"]
console.log(claims.jti);   // "550e8400-e29b-41d4-..."
```

---

## Revocation

### Interface: `RevocationRegistry`

```typescript
interface RevocationRegistry {
  revoke(jti: string): void;
  isRevoked(jti: string): boolean;
}
```

Implement this interface to build a custom revocation backend. The two methods must be idempotent and synchronous.

| Method | Description |
|--------|-------------|
| `revoke(jti)` | Mark a token JTI as revoked. Idempotent. |
| `isRevoked(jti)` | Return `true` if the JTI has been revoked. |

---

### Class: `InMemoryRevocationRegistry`

```typescript
class InMemoryRevocationRegistry implements RevocationRegistry {
  revoke(jti: string): void
  isRevoked(jti: string): boolean
}
```

In-process revocation backed by a `Set<string>`. State is lost when the process terminates. Suitable for tests and short-lived agents.

**No constructor parameters.**

**Example:**
```typescript
import { InMemoryRevocationRegistry } from "@agentpassport/core";

const registry = new InMemoryRevocationRegistry();
registry.revoke("abc-uuid");

console.log(registry.isRevoked("abc-uuid")); // true
console.log(registry.isRevoked("other"));     // false

// Idempotent
registry.revoke("abc-uuid"); // no error
console.log(registry.isRevoked("abc-uuid")); // still true
```

---

## Trust

### Class: `ScopeError`

```typescript
class ScopeError extends Error {
  readonly capability: string;
  readonly required: string[];
  readonly granted: string[];
  readonly name: "ScopeError";
  readonly message: string;
}
```

Thrown by `TrustMiddleware.check()` and propagated through `Agent.handle()` when the auth chain doesn't grant the required scope.

**Constructor (internal):**
```typescript
new ScopeError(capability: string, required: string[], granted: string[])
```

| Property | Type | Description |
|----------|------|-------------|
| `capability` | `string` | The capability name that failed the check |
| `required` | `string[]` | The scope strings that were required |
| `granted` | `string[]` | The scope strings that were actually granted |
| `message` | `string` | Human-readable message including `capability`, missing scopes |
| `name` | `"ScopeError"` | Discriminant for `instanceof` checks |

**Example:**
```typescript
import { Agent, ScopeError } from "@agentpassport/core";

try {
  await agent.handle(task);
} catch (e) {
  if (e instanceof ScopeError) {
    console.log(e.capability);  // "read_customers"
    console.log(e.required);    // ["read:db:customers"]
    console.log(e.granted);     // ["write:cache"]
    // Return 403 to caller
  }
}
```

---

### Class: `TrustMiddleware`

```typescript
class TrustMiddleware {
  constructor(
    agentDid: string,
    knownPublicKeys: Map<string, Uint8Array>,
    capabilityScopes: Map<string, string[]>,
    revocationRegistry?: RevocationRegistry
  )
  check(authChain: string[], capabilityName: string): void
}
```

Pre-execution scope enforcement. Wired automatically inside `Agent`. You typically don't instantiate this directly.

### Constructor

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agentDid` | `string` | Yes | — | DID of the agent. Tokens with `sub !== agentDid` are skipped. |
| `knownPublicKeys` | `Map<string, Uint8Array>` | Yes | — | Issuer DID → public key. Passed by reference — mutations are reflected. |
| `capabilityScopes` | `Map<string, string[]>` | Yes | — | Capability name → required scopes. Passed by reference. |
| `revocationRegistry` | `RevocationRegistry` | No | `undefined` | Optional revocation registry for token validity checks. |

### `TrustMiddleware.check()`

```typescript
check(authChain: string[], capabilityName: string): void
```

Check that the auth chain grants the required scope for a capability.

**Logic:**
1. If `capabilityScopes.get(capabilityName)` is empty/undefined → return (no-op).
2. Iterate tokens:
   - Skip tokens where `sub !== agentDid` or issuer is unknown.
   - Verify via `verifyAuthChain` (single-token chain against self).
   - Accumulate granted scopes.
3. If `"*"` in granted → return (pass).
4. If any required scope is missing → throw `ScopeError`.
5. If chain is empty and scopes required → throw `ScopeError`.

**Throws:** `ScopeError` if scope check fails.

**Returns:** `void`

---

## Agent

### Type: `CapabilityHandler`

```typescript
type CapabilityHandler = (task: TaskEnvelope) => Promise<Record<string, unknown>>;
```

The function signature all capability handlers must conform to.

| Parameter | Type | Description |
|-----------|------|-------------|
| `task` | `TaskEnvelope` | The incoming task to handle |

**Returns:** `Promise<Record<string, unknown>>` — the result object to return to the caller.

---

### Interface: `CapabilityOptions`

```typescript
interface CapabilityOptions {
  requires?: string[];
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `requires` | `string[]` | No | `[]` | Scope strings the auth chain must grant. If empty or omitted, no scope check is performed. |

---

### Interface: `DelegateOptions`

```typescript
interface DelegateOptions {
  targetDid: string;
  scope?: string[];
  ttlSeconds?: number;
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `targetDid` | `string` | Yes | — | DID of the target agent (`sub` in the new JWT) |
| `scope` | `string[]` | No | `["*"]` | Scopes to grant in the delegation token |
| `ttlSeconds` | `number` | No | `3600` | Token validity in seconds |

---

### Class: `Agent`

```typescript
class Agent {
  readonly name: string;
  readonly did: string;
  readonly publicKey: Uint8Array;

  constructor(name: string, opts?: { privateKey?: Uint8Array; revocationRegistry?: RevocationRegistry })
  capability(name: string, options: CapabilityOptions, handler: CapabilityHandler): this
  trustKeys(keys: Map<string, Uint8Array> | Record<string, Uint8Array>): void
  async handle(task: TaskEnvelope): Promise<Record<string, unknown>>
  delegate(task: TaskEnvelope, opts: DelegateOptions): TaskEnvelope
}
```

The central class. Owns an Ed25519 keypair, a DID, capability handlers, trusted keys, and a trust middleware instance.

#### Constructor

```typescript
new Agent(
  name: string,
  opts?: {
    privateKey?: Uint8Array;
    revocationRegistry?: RevocationRegistry;
  }
)
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `string` | Yes | — | Human-readable agent name |
| `opts.privateKey` | `Uint8Array` | No | auto-generated | 64-byte keypair (seed+pubkey) or 32-byte seed. If omitted, a fresh keypair is generated. |
| `opts.revocationRegistry` | `RevocationRegistry` | No | `undefined` | Revocation registry passed to `TrustMiddleware`. |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `name` | `string` | Agent name |
| `did` | `string` | `did:key:z...` derived from public key |
| `publicKey` | `Uint8Array` | 32-byte Ed25519 public key |

**Example 1: Auto-generate keypair**
```typescript
import { Agent } from "@agentpassport/core";

const agent = new Agent("summarizer");
console.log(agent.did);        // did:key:z6Mk...
console.log(agent.publicKey.length); // 32
```

**Example 2: Restore from persisted key**
```typescript
import { readFileSync } from "fs";

const seed = new Uint8Array(readFileSync("agent.seed"));
const agent = new Agent("summarizer", { privateKey: seed });
// Same DID as when seed was first generated
```

**Example 3: With revocation registry**
```typescript
import { Agent, InMemoryRevocationRegistry } from "@agentpassport/core";

const registry = new InMemoryRevocationRegistry();
const agent = new Agent("worker", { revocationRegistry: registry });
```

---

#### `Agent.capability()`

```typescript
capability(
  name: string,
  options: CapabilityOptions,
  handler: CapabilityHandler
): this
```

Register a capability handler. Returns `this` for method chaining.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `string` | Yes | Capability name matched against `task.intent.type` |
| `options` | `CapabilityOptions` | Yes | `{ requires?: string[] }` — pass `{}` for no scope requirement |
| `handler` | `CapabilityHandler` | Yes | Async function `(task) => Promise<Record<string, unknown>>` |

**Returns:** `this` — supports method chaining.

**Throws (at call time):** Nothing at registration. At dispatch (via `handle()`):
- `ScopeError` if scope check fails
- Any error thrown by `handler`

**Example 1: No scope (public capability)**
```typescript
agent.capability("ping", {}, async (task) => {
  return { pong: true };
});
```

**Example 2: Scoped capability**
```typescript
agent.capability(
  "read_customers",
  { requires: ["read:db:customers"] },
  async (task) => {
    const rows = await db.query("SELECT * FROM customers");
    return { rows };
  }
);
```

**Example 3: Method chaining**
```typescript
const agent = new Agent("multi-skill")
  .capability("ping", {}, async () => ({ pong: true }))
  .capability("echo", {}, async (task) => ({ echo: task.intent.params }))
  .capability(
    "secure_op",
    { requires: ["admin:*"] },
    async (task) => ({ done: true })
  );
```

---

#### `Agent.trustKeys()`

```typescript
trustKeys(keys: Map<string, Uint8Array> | Record<string, Uint8Array>): void
```

Register trusted issuer public keys for auth chain verification.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `keys` | `Map<string, Uint8Array> \| Record<string, Uint8Array>` | Yes | Mapping from issuer DID to 32-byte public key. |

**Returns:** `void`

**Throws:** Nothing.

**Example 1: Trust an orchestrator using a Map**
```typescript
agent.trustKeys(new Map([
  [orchestrator.did, orchestrator.publicKey],
]));
```

**Example 2: Trust multiple agents using an object**
```typescript
agent.trustKeys({
  [orchestrator.did]: orchestrator.publicKey,
  [supervisor.did]:   supervisor.publicKey,
});
```

**Example 3: Trust derived from DID (no out-of-band key exchange)**
```typescript
import { parseDid } from "@agentpassport/core";

const issuerDid = "did:key:z6Mk...";
const issuerPub = parseDid(issuerDid); // public key is in the DID

agent.trustKeys({ [issuerDid]: issuerPub });
```

---

#### `Agent.handle()`

```typescript
async handle(task: TaskEnvelope): Promise<Record<string, unknown>>
```

Handle an incoming task. Runs scope check then dispatches to the registered handler.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | `TaskEnvelope` | Yes | The incoming task to handle |

**Returns:** `Promise<Record<string, unknown>>` — the result returned by the handler.

**Throws:**
- `Error` with message `"No handler for capability: <type>"` if no handler is registered for `task.intent.type`.
- `ScopeError` if the auth chain doesn't cover the required scope.
- Any error thrown by the handler.

**Note:** Unlike the Python SDK, the TypeScript `Agent.handle()` does not manage task lifecycle state or emit observability events automatically. You can build these on top using a wrapper.

**Example 1: Express/HTTP server**
```typescript
import express from "express";
import { Agent, TaskEnvelope, ScopeError } from "@agentpassport/core";

const app = express();
app.use(express.json());

const agent = new Agent("worker");
agent.capability("compute", {}, async (task) => ({ result: 42 }));

app.post("/agentpassport/tasks", async (req, res) => {
  const task = req.body as TaskEnvelope;
  try {
    const result = await agent.handle(task);
    res.json(result);
  } catch (e) {
    if (e instanceof ScopeError) res.status(403).json({ error: e.message });
    else res.status(500).json({ error: String(e) });
  }
});
```

**Example 2: Handling unknown capability**
```typescript
const task: TaskEnvelope = {
  version: "1.0",
  id: "task_123",
  intent: { type: "unknown_capability", params: {} },
  constraints: { budget_credits: 100, max_delegations: 5, allowed_capabilities: [], denied_capabilities: [] },
  auth_chain: [],
  trace_id: "trace_abc",
  state: "created",
};

try {
  await agent.handle(task);
} catch (e) {
  console.log(e.message); // "No handler for capability: unknown_capability"
}
```

---

#### `Agent.delegate()`

```typescript
delegate(task: TaskEnvelope, opts: DelegateOptions): TaskEnvelope
```

Sign a new delegation JWT and return a new `TaskEnvelope` with the extended `auth_chain`. **Does not send the task** — the TypeScript SDK separates delegation (signing) from sending (transport), leaving HTTP logic to the caller.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | `TaskEnvelope` | Yes | The task to delegate. Original is not mutated. |
| `opts` | `DelegateOptions` | Yes | Target DID, scope, TTL |

**Returns:** `TaskEnvelope` — a new task with:
- `auth_chain` extended with the new JWT
- `state` set to `"delegated"`

**Throws:** Nothing.

**Example 1: Delegate and send**
```typescript
import { Agent, createTask } from "@agentpassport/core";

const orchestrator = new Agent("orchestrator");
const worker = new Agent("worker");
orchestrator.trustKeys({ [orchestrator.did]: orchestrator.publicKey });
worker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });

const task = createTask({ type: "process", params: { data: "..." } });

const delegated = orchestrator.delegate(task, {
  targetDid: worker.did,
  scope: ["process:data"],
  ttlSeconds: 3600,
});

// Send via fetch
const response = await fetch("http://worker:8080/agentpassport/tasks", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(delegated),
});
const result = await response.json();
```

**Example 2: Multi-hop delegation**
```typescript
const task = createTask({ type: "root", params: {} });

const toA = orchestrator.delegate(task, { targetDid: agentA.did, scope: ["*"] });
const toB = agentA.delegate(toA, { targetDid: agentB.did, scope: ["read:db"] });

console.log(toB.auth_chain.length); // 2
console.log(toB.state);             // "delegated"
```

---

## Types

### Type: `TaskState`

```typescript
type TaskState =
  | "created"
  | "delegated"
  | "accepted"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";
```

String union type matching the Python SDK's `TaskState` enum. Used in `TaskEnvelope.state`.

---

### Interface: `Intent`

```typescript
interface Intent {
  type: string;
  params: Record<string, unknown>;
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Capability name to invoke |
| `params` | `Record<string, unknown>` | Parameters passed to the handler |

---

### Interface: `Constraints`

```typescript
interface Constraints {
  budget_credits: number;
  deadline_ms?: number;
  max_delegations: number;
  allowed_capabilities: string[];
  denied_capabilities: string[];
}
```

| Field | Type | Required | Default (via `createTask`) | Description |
|-------|------|----------|---------------------------|-------------|
| `budget_credits` | `number` | Yes | `100` | Total credits for this task |
| `deadline_ms` | `number` | No | `undefined` | Deadline in ms since epoch |
| `max_delegations` | `number` | Yes | `5` | Remaining delegation depth |
| `allowed_capabilities` | `string[]` | Yes | `[]` | Whitelist (empty = all allowed) |
| `denied_capabilities` | `string[]` | Yes | `[]` | Blacklist |

---

### Interface: `TaskEnvelope`

```typescript
interface TaskEnvelope {
  version: "1.0";
  id: string;
  parent_id?: string;
  intent: Intent;
  constraints: Constraints;
  /** List of EdDSA JWT strings forming the delegation chain */
  auth_chain: string[];
  trace_id: string;
  state: TaskState;
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | `"1.0"` | Yes | Protocol version literal |
| `id` | `string` | Yes | Unique task ID |
| `parent_id` | `string` | No | Parent task ID for subtask trees |
| `intent` | `Intent` | Yes | What to do |
| `constraints` | `Constraints` | Yes | Budget and delegation limits |
| `auth_chain` | `string[]` | Yes | Delegation JWT chain |
| `trace_id` | `string` | Yes | Distributed trace ID |
| `state` | `TaskState` | Yes | Lifecycle state |

---

### `createTask()`

```typescript
function createTask(
  intent: Intent,
  overrides?: Partial<Omit<TaskEnvelope, "version" | "intent">>
): TaskEnvelope
```

Convenience factory for creating a new `TaskEnvelope` with sensible defaults. Uses `crypto.randomUUID()` for `id` and `trace_id`.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `intent` | `Intent` | Yes | — | The task's intent |
| `overrides` | `Partial<Omit<TaskEnvelope, "version" \| "intent">>` | No | `{}` | Override any field except `version` and `intent` |

**Default values applied:**
```typescript
{
  version: "1.0",
  id: crypto.randomUUID(),
  intent: <provided>,
  constraints: {
    budget_credits: 100,
    max_delegations: 5,
    allowed_capabilities: [],
    denied_capabilities: [],
  },
  auth_chain: [],
  trace_id: crypto.randomUUID(),
  state: "created",
}
```

**Returns:** `TaskEnvelope`

**Throws:** Nothing.

**Example 1: Basic task creation**
```typescript
import { createTask } from "@agentpassport/core";

const task = createTask({ type: "summarize", params: { text: "Hello world" } });
console.log(task.state);                     // "created"
console.log(task.constraints.budget_credits); // 100
```

**Example 2: Override budget and deadline**
```typescript
const task = createTask(
  { type: "heavy_computation", params: { iterations: 1000 } },
  {
    constraints: {
      budget_credits: 500,
      max_delegations: 2,
      deadline_ms: Date.now() + 60_000, // 1 minute from now
      allowed_capabilities: [],
      denied_capabilities: [],
    },
  }
);
```

**Example 3: Override state for testing**
```typescript
const task = createTask(
  { type: "ping", params: {} },
  { state: "accepted" }
);
console.log(task.state); // "accepted"
```

---

## Internal helpers

These are internal functions not exported from `src/index.ts` but documented here for completeness.

### `b64urlEncode(data: Uint8Array): string`

Standard base64url encoding without padding. Used for JWT parts.

### `b64urlDecode(s: string): Uint8Array`

Inverse of `b64urlEncode`. Re-adds padding before decoding via `atob`.

### `encodeJwt(claims: Record<string, unknown>, seed: Uint8Array): string`

Internal JWT encoder. Sorts claim keys, JSON-serializes, base64url-encodes header and payload, signs with `@noble/ed25519`, and returns the compact representation.

### `decodeJwtClaims(token: string): Record<string, unknown>`

Decode JWT payload without signature verification. Exported publicly — see [`decodeJwtClaims()`](#decodejwtclaims).

### `verifyJwtSignature(token: string, publicKeyBytes: Uint8Array): Record<string, unknown>`

Verify JWT signature using `@noble/ed25519` and return decoded claims. Throws on structural errors or invalid signature.

### `_chain_granted_scopes` equivalent (inline in `TrustMiddleware.check()`)

The TypeScript implementation inlines the granted-scope accumulation logic inside `TrustMiddleware.check()` rather than extracting it as a separate function. For each token in the auth chain whose `sub === agentDid` and whose issuer is known, it calls `verifyAuthChain` on that single token and accumulates scopes if valid.
