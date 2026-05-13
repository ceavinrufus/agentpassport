# Guide: Building Your First AgentPassport Agent (TypeScript)

Complete, runnable guide for using `@agentpassport/core`. Every code block is a complete file you can copy-paste and run.

---

## Prerequisites

```bash
npm install @agentpassport/core
# TypeScript setup
npm install -D typescript @types/node tsx
npx tsc --init   # creates tsconfig.json
```

Recommended `tsconfig.json` options:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true
  }
}
```

Run any example with: `npx tsx <file>.ts`

---

## Step 1: Single agent, single capability

The simplest case — one agent, one capability, no delegation, no scopes.

```typescript
// step1-single-agent.ts

import { Agent, createTask } from "@agentpassport/core";

const agent = new Agent("echo-agent");

console.log(`Agent DID: ${agent.did}`);
// did:key:z6Mk...  (different each run)

agent.capability("echo", {}, async (task) => {
  const message = (task.intent.params.message as string) ?? "";
  return { echoed: message, from: agent.did };
});

const task = createTask({ type: "echo", params: { message: "Hello, AgentPassport!" } });

const result = await agent.handle(task);
console.log(result);
// { echoed: 'Hello, AgentPassport!', from: 'did:key:z6Mk...' }
```

---

## Step 2: Two agents with delegation

Orchestrator delegates to worker via a signed JWT.

```typescript
// step2-delegation.ts

import {
  Agent,
  createTask,
  signDelegation,
  verifyAuthChain,
  ScopeError,
} from "@agentpassport/core";

// ── Create two agents ────────────────────────────────────────────────────────

const orchestrator = new Agent("orchestrator");
const worker = new Agent("worker");

console.log(`Orchestrator: ${orchestrator.did}`);
console.log(`Worker:       ${worker.did}`);

// Worker trusts orchestrator's key.
// In production: from a registry or shared config.
worker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });

// ── Worker capability (requires scope) ───────────────────────────────────────

worker.capability(
  "process_data",
  { requires: ["process:data"] },
  async (task) => {
    const payload = (task.intent.params.payload as string) ?? "";
    return { processed: payload.toUpperCase(), by: worker.did };
  }
);

// ── Happy path: valid delegation ─────────────────────────────────────────────

const task = createTask(
  { type: "process_data", params: { payload: "hello world" } },
  { constraints: { budget_credits: 100, max_delegations: 5, allowed_capabilities: [], denied_capabilities: [] } }
);

// Orchestrator signs a delegation JWT and appends it to the auth chain
const delegatedTask = orchestrator.delegate(task, {
  targetDid: worker.did,
  scope: ["process:data"],
  ttlSeconds: 3600,
});

console.log(`\nAuth chain length: ${delegatedTask.auth_chain.length}`);  // 1

// Verify manually (what worker.handle() does internally)
const ok = verifyAuthChain({
  chain: delegatedTask.auth_chain,
  expectedSubject: worker.did,
  knownPublicKeys: new Map([[orchestrator.did, orchestrator.publicKey]]),
});
console.log(`Chain valid: ${ok}`);  // true

const result = await worker.handle(delegatedTask);
console.log(`\nResult: ${JSON.stringify(result)}`);
// { processed: 'HELLO WORLD', by: 'did:key:z6Mk...' }

// ── Unhappy path: no auth chain ──────────────────────────────────────────────

const taskNoAuth = createTask({ type: "process_data", params: { payload: "test" } });

try {
  await worker.handle(taskNoAuth);
} catch (e) {
  if (e instanceof ScopeError) {
    console.log(`\nExpected ScopeError: ${e.message}`);
    // Scope denied for capability "process_data": requires [process:data], missing [process:data]
  }
}
```

---

## Step 3: HTTP server using Express

```typescript
// step3-http-worker.ts
// Run with: npx tsx step3-http-worker.ts

import express, { Request, Response } from "express";
import {
  Agent,
  TaskEnvelope,
  ScopeError,
  generateKeypair,
} from "@agentpassport/core";

// ── Agent setup ───────────────────────────────────────────────────────────────

// To restore a persistent identity:
//   import { readFileSync } from "fs";
//   const seed = new Uint8Array(readFileSync("agent.seed"));
//   const agent = new Agent("worker", { privateKey: seed });

const agent = new Agent("data-worker");
console.log(`Worker DID (share with orchestrators): ${agent.did}`);
console.log(`Worker public key (hex): ${Buffer.from(agent.publicKey).toString("hex")}`);

// ── Capabilities ─────────────────────────────────────────────────────────────

agent.capability(
  "summarize",
  { requires: ["invoke:llm"] },
  async (task) => {
    const text = (task.intent.params.text as string) ?? "";
    // In real code: call an LLM API here
    return {
      summary: `Summary: ${text.slice(0, 50)}...`,
      tokens_used: text.split(/\s+/).length,
      agent: agent.did,
    };
  }
);

agent.capability("health_check", {}, async (task) => {
  return { status: "ok", agent: agent.did };
});

// ── Register trusted issuers from environment ─────────────────────────────────

const trustedDid = process.env.TRUSTED_ORCHESTRATOR_DID;
const trustedPubHex = process.env.TRUSTED_ORCHESTRATOR_PUB_HEX;
if (trustedDid && trustedPubHex) {
  agent.trustKeys({ [trustedDid]: new Uint8Array(Buffer.from(trustedPubHex, "hex")) });
  console.log(`Trusted orchestrator: ${trustedDid}`);
} else {
  console.warn("WARNING: No trusted orchestrator configured. Scoped capabilities will reject all tasks.");
}

// ── Express server ────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

app.post("/agentpassport/tasks", async (req: Request, res: Response) => {
  const task = req.body as TaskEnvelope;

  try {
    const result = await agent.handle(task);
    res.json(result);
  } catch (e) {
    if (e instanceof ScopeError) {
      res.status(403).json({ error: "scope_denied", message: e.message });
    } else if (e instanceof Error && e.message.startsWith("No handler")) {
      res.status(404).json({ error: "unknown_capability", message: e.message });
    } else {
      res.status(500).json({ error: "internal_error", message: String(e) });
    }
  }
});

app.get("/agentpassport/agent-card", (_req, res) => {
  res.json({
    did: agent.did,
    name: "data-worker",
    capabilities: ["summarize", "health_check"],
    endpoint: "http://localhost:8001",
    transports: ["http"],
  });
});

app.listen(8001, () => console.log("Worker listening on :8001"));
```

---

## Step 4: Orchestrator that delegates to the HTTP worker

```typescript
// step4-orchestrator.ts

import { Agent, createTask, ScopeError } from "@agentpassport/core";
import type { TaskEnvelope } from "@agentpassport/core";

const orchestrator = new Agent("orchestrator");
console.log(`Orchestrator DID: ${orchestrator.did}`);
console.log(`Orchestrator pub (hex): ${Buffer.from(orchestrator.publicKey).toString("hex")}`);

// Set these from the output of step3-http-worker.ts
const WORKER_DID = process.env.WORKER_DID ?? "did:key:z6Mk...";
const WORKER_PUB_HEX = process.env.WORKER_PUB_HEX ?? "";
const WORKER_ENDPOINT = "http://localhost:8001";

async function sendTask(task: TaskEnvelope, endpoint: string): Promise<unknown> {
  const response = await fetch(`${endpoint}/agentpassport/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(task),
  });
  if (!response.ok) {
    const body = await response.json();
    throw new Error(`${response.status}: ${JSON.stringify(body)}`);
  }
  return response.json();
}

async function runSummarization(text: string): Promise<unknown> {
  const task = createTask(
    { type: "summarize", params: { text } },
    {
      constraints: {
        budget_credits: 50,
        max_delegations: 3,
        allowed_capabilities: [],
        denied_capabilities: [],
      },
    }
  );

  console.log(`Task ID: ${task.id}`);
  console.log(`Trace ID: ${task.trace_id}`);

  // Register worker's public key as trusted (so we know the DID is valid)
  // In production: derive from the DID itself or fetch from registry
  if (WORKER_PUB_HEX) {
    orchestrator.trustKeys({
      [WORKER_DID]: new Uint8Array(Buffer.from(WORKER_PUB_HEX, "hex")),
    });
  }

  // Delegate — signs JWT and returns extended task
  const delegated = orchestrator.delegate(task, {
    targetDid: WORKER_DID,
    scope: ["invoke:llm"],
    ttlSeconds: 600,
  });

  return sendTask(delegated, WORKER_ENDPOINT);
}

const result = await runSummarization(
  "AgentPassport gives AI agents cryptographically verifiable identities."
);
console.log("Result:", result);
```

---

## Step 5: Three-hop delegation chain

```typescript
// step5-three-hop.ts

import {
  Agent,
  createTask,
  signDelegation,
  ScopeError,
} from "@agentpassport/core";
import type { TaskEnvelope } from "@agentpassport/core";

// ── Three agents ──────────────────────────────────────────────────────────────

const orchestrator = new Agent("orchestrator");
const analyzer = new Agent("analyzer");
const dbReader = new Agent("db-reader");

// ── Trust setup ───────────────────────────────────────────────────────────────

analyzer.trustKeys({ [orchestrator.did]: orchestrator.publicKey });
dbReader.trustKeys({
  [orchestrator.did]: orchestrator.publicKey,
  [analyzer.did]: analyzer.publicKey,
});

// ── Capabilities ──────────────────────────────────────────────────────────────

dbReader.capability(
  "read_customers",
  { requires: ["read:db:customers"] },
  async (task) => {
    const limit = (task.intent.params.limit as number) ?? 10;
    const rows = Array.from({ length: limit }, (_, i) => ({
      id: i,
      name: `Customer ${i}`,
    }));
    return { rows, count: rows.length };
  }
);

analyzer.capability(
  "analyze_customers",
  { requires: ["analyze:customers"] },
  async (task) => {
    // Analyzer delegates the DB read to dbReader
    const subTask: TaskEnvelope = {
      version: "1.0",
      id: crypto.randomUUID(),
      parent_id: task.id,
      intent: { type: "read_customers", params: { limit: 5 } },
      constraints: {
        budget_credits: task.constraints.budget_credits - 10,
        max_delegations: task.constraints.max_delegations - 1,
        allowed_capabilities: [],
        denied_capabilities: [],
      },
      auth_chain: [...task.auth_chain], // inherit chain
      trace_id: task.trace_id,
      state: "created",
    };

    // Analyzer signs delegation to dbReader
    const delegated = analyzer.delegate(subTask, {
      targetDid: dbReader.did,
      scope: ["read:db:customers"],
      ttlSeconds: 300,
    });

    // In production: send via HTTP. Here: call directly.
    const dbResult = await dbReader.handle(delegated);
    const count = (dbResult.count as number) ?? 0;

    return {
      analysis: `Found ${count} customers.`,
      raw_count: count,
    };
  }
);

// ── Main flow ─────────────────────────────────────────────────────────────────

const task = createTask(
  { type: "analyze_customers", params: {} },
  {
    constraints: {
      budget_credits: 100,
      max_delegations: 5,
      allowed_capabilities: [],
      denied_capabilities: [],
    },
  }
);

// Orchestrator delegates to analyzer with broad scope
const orch_to_analyzer = signDelegation({
  issuerPrivateKey: orchestrator["_privateKey"],  // access private field for demo
  issuerDid: orchestrator.did,
  subjectDid: analyzer.did,
  scope: ["analyze:customers", "read:db:customers"],
  ttlSeconds: 3600,
});
task.auth_chain.push(orch_to_analyzer);

console.log(`Auth chain before analyzer: ${task.auth_chain.length} token(s)`);

const result = await analyzer.handle(task);
console.log(`\nResult: ${JSON.stringify(result)}`);
// { analysis: 'Found 5 customers.', raw_count: 5 }

// ── Scope failure demo ────────────────────────────────────────────────────────

const narrowTask = createTask(
  { type: "analyze_customers", params: {} },
  {
    constraints: {
      budget_credits: 100,
      max_delegations: 5,
      allowed_capabilities: [],
      denied_capabilities: [],
    },
  }
);

const narrowToken = signDelegation({
  issuerPrivateKey: orchestrator["_privateKey"],
  issuerDid: orchestrator.did,
  subjectDid: analyzer.did,
  scope: ["something_else"], // doesn't include analyze:customers
  ttlSeconds: 3600,
});
narrowTask.auth_chain.push(narrowToken);

try {
  await analyzer.handle(narrowTask);
} catch (e) {
  if (e instanceof ScopeError) {
    console.log(`\nScopeError (expected): ${e.message}`);
    console.log(`Required: ${JSON.stringify(e.required)}`);
    console.log(`Granted:  ${JSON.stringify(e.granted)}`);
  }
}
```

---

## Step 6: Revocation

```typescript
// step6-revocation.ts

import {
  Agent,
  createTask,
  signDelegation,
  verifyAuthChain,
  decodeJwtClaims,
  InMemoryRevocationRegistry,
} from "@agentpassport/core";

const orchestrator = new Agent("orchestrator");
const worker = new Agent("worker");
worker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });

const registry = new InMemoryRevocationRegistry();

worker.capability(
  "sensitive_op",
  { requires: ["exec:sensitive"] },
  async () => ({ done: true })
);

// 1. Issue a token
const token = signDelegation({
  issuerPrivateKey: orchestrator["_privateKey"],
  issuerDid: orchestrator.did,
  subjectDid: worker.did,
  scope: ["exec:sensitive"],
  ttlSeconds: 3600,
});

const claims = decodeJwtClaims(token);
const jti = claims.jti as string;
console.log(`JTI: ${jti}`);

const task = createTask({ type: "sensitive_op", params: {} });
task.auth_chain.push(token);

// 2. Verify before revocation — passes
const okBefore = verifyAuthChain({
  chain: task.auth_chain,
  expectedSubject: worker.did,
  knownPublicKeys: new Map([[orchestrator.did, orchestrator.publicKey]]),
  revocationRegistry: registry,
});
console.log(`Valid before revocation: ${okBefore}`);  // true

// 3. Revoke
registry.revoke(jti);
console.log(`Revoked: ${jti}`);

// 4. Verify after revocation — fails
const okAfter = verifyAuthChain({
  chain: task.auth_chain,
  expectedSubject: worker.did,
  knownPublicKeys: new Map([[orchestrator.did, orchestrator.publicKey]]),
  revocationRegistry: registry,
});
console.log(`Valid after revocation: ${okAfter}`);  // false

// 5. New token works fine
const newToken = signDelegation({
  issuerPrivateKey: orchestrator["_privateKey"],
  issuerDid: orchestrator.did,
  subjectDid: worker.did,
  scope: ["exec:sensitive"],
  ttlSeconds: 3600,
});

const newWorker = new Agent("worker-new", { privateKey: worker["_privateKey"] });
newWorker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });
newWorker.capability("sensitive_op", { requires: ["exec:sensitive"] }, async () => ({ done: true }));

const newTask = createTask({ type: "sensitive_op", params: {} });
newTask.auth_chain.push(newToken);

const result = await newWorker.handle(newTask);
console.log(`New token works: ${JSON.stringify(result)}`);  // { done: true }
```

---

## Step 7: Cross-SDK compatibility — TypeScript verifying Python tokens

```typescript
// step7-cross-sdk.ts
// Demonstrates that tokens produced by the Python SDK verify correctly in TypeScript.
// Run the Python script first to get the token, then paste it below.

import { verifyAuthChain, parseDid, decodeJwtClaims } from "@agentpassport/core";

// ── Paste the output of this Python snippet: ──────────────────────────────────
// from agentpassport import generate_keypair, did_from_public_key, sign_delegation
// priv, pub = generate_keypair()
// did = did_from_public_key(pub)
// _, sub_pub = generate_keypair()
// sub_did = did_from_public_key(sub_pub)
// token = sign_delegation(priv, did, sub_did, ["read:db"], ttl_seconds=86400)
// print(f"issuer_did={did}")
// print(f"subject_did={sub_did}")
// print(f"token={token}")

// Replace these with actual values from the Python output:
const ISSUER_DID = "did:key:z6Mk...";
const SUBJECT_DID = "did:key:z6Mk...";
const TOKEN = "eyJ...";

// Derive public key from DID (no out-of-band key exchange needed for did:key)
const issuerPub = parseDid(ISSUER_DID);

// Decode and inspect
const claims = decodeJwtClaims(TOKEN);
console.log("Decoded claims:", claims);
// { iss: '...', sub: '...', iat: ..., exp: ..., jti: '...', scope: ['read:db'], max_delegations: 0 }

// Verify
const ok = verifyAuthChain({
  chain: [TOKEN],
  expectedSubject: SUBJECT_DID,
  knownPublicKeys: new Map([[ISSUER_DID, issuerPub]]),
});

console.log(`Python → TypeScript verification: ${ok}`);  // true
```

---

## Step 8: Complete production example

All features together: multiple agents, scope enforcement, revocation, method chaining.

```typescript
// step8-complete.ts

import {
  Agent,
  createTask,
  signDelegation,
  verifyAuthChain,
  decodeJwtClaims,
  InMemoryRevocationRegistry,
  ScopeError,
  parseDid,
} from "@agentpassport/core";
import type { TaskEnvelope } from "@agentpassport/core";

// ══════════════════════════════════════════════════════════════
// 1. SETUP
// ══════════════════════════════════════════════════════════════

const revocationRegistry = new InMemoryRevocationRegistry();

const orchestrator = new Agent("orchestrator", { revocationRegistry });
const analyzer = new Agent("analyzer", { revocationRegistry });
const dbReader = new Agent("db-reader", { revocationRegistry });

console.log("=== Agent Identities ===");
[orchestrator, analyzer, dbReader].forEach((a) => {
  console.log(`${a.name}: ${a.did}`);
});

// ── Trust setup ───────────────────────────────────────────────────────────────

analyzer.trustKeys({ [orchestrator.did]: orchestrator.publicKey });
dbReader.trustKeys({
  [orchestrator.did]: orchestrator.publicKey,
  [analyzer.did]: analyzer.publicKey,
});

// ══════════════════════════════════════════════════════════════
// 2. CAPABILITIES (method chaining)
// ══════════════════════════════════════════════════════════════

dbReader
  .capability(
    "read_db",
    { requires: ["read:db"] },
    async (task) => {
      const table = (task.intent.params.table as string) ?? "records";
      const limit = (task.intent.params.limit as number) ?? 5;
      const rows = Array.from({ length: limit }, (_, i) => ({
        id: i,
        table,
        value: Math.floor(Math.random() * 100),
      }));
      return { rows, count: rows.length, table };
    }
  )
  .capability("health_check", {}, async () => ({ status: "ok", agent: dbReader.did }));

analyzer
  .capability(
    "analyze",
    { requires: ["invoke:analyze"] },
    async (task) => {
      // Delegate DB read to dbReader
      const subTask: TaskEnvelope = {
        version: "1.0",
        id: crypto.randomUUID(),
        parent_id: task.id,
        intent: { type: "read_db", params: { table: "sales", limit: 10 } },
        constraints: {
          budget_credits: 30,
          max_delegations: task.constraints.max_delegations - 1,
          allowed_capabilities: [],
          denied_capabilities: [],
        },
        auth_chain: [...task.auth_chain],
        trace_id: task.trace_id,
        state: "created",
      };

      const delegated = analyzer.delegate(subTask, {
        targetDid: dbReader.did,
        scope: ["read:db"],
        ttlSeconds: 300,
      });

      const dbResult = await dbReader.handle(delegated);
      const rows = dbResult.rows as Array<{ value: number }>;
      const total = rows.reduce((sum, r) => sum + r.value, 0);

      return {
        row_count: rows.length,
        total_value: total,
        average_value: rows.length > 0 ? total / rows.length : 0,
        trace_id: task.trace_id,
      };
    }
  );

// ══════════════════════════════════════════════════════════════
// 3. HAPPY PATH
// ══════════════════════════════════════════════════════════════

async function runHappyPath(): Promise<void> {
  console.log("\n=== Happy Path ===");

  const task = createTask(
    { type: "analyze", params: {} },
    {
      constraints: {
        budget_credits: 100,
        max_delegations: 5,
        allowed_capabilities: [],
        denied_capabilities: [],
      },
    }
  );
  console.log(`Task: ${task.id} | Trace: ${task.trace_id}`);

  // Orchestrator delegates to analyzer
  const delegated = orchestrator.delegate(task, {
    targetDid: analyzer.did,
    scope: ["invoke:analyze", "read:db"],
    ttlSeconds: 3600,
  });

  // Verify chain
  const ok = verifyAuthChain({
    chain: delegated.auth_chain,
    expectedSubject: analyzer.did,
    knownPublicKeys: new Map([[orchestrator.did, orchestrator.publicKey]]),
    revocationRegistry,
  });
  console.log(`Chain verified: ${ok}`);

  const result = await analyzer.handle(delegated);
  console.log(`Result: rows=${result.row_count}, total=${result.total_value}, avg=${(result.average_value as number).toFixed(1)}`);
}

// ══════════════════════════════════════════════════════════════
// 4. SCOPE ENFORCEMENT
// ══════════════════════════════════════════════════════════════

async function runScopeTest(): Promise<void> {
  console.log("\n=== Scope Enforcement ===");

  const task = createTask({ type: "analyze", params: {} }, {
    constraints: { budget_credits: 100, max_delegations: 5, allowed_capabilities: [], denied_capabilities: [] },
  });

  // Insufficient scope — missing invoke:analyze
  const badDelegated = orchestrator.delegate(task, {
    targetDid: analyzer.did,
    scope: ["read:db"],  // missing invoke:analyze
  });

  try {
    await analyzer.handle(badDelegated);
    console.log("ERROR: Should have thrown ScopeError");
  } catch (e) {
    if (e instanceof ScopeError) {
      console.log(`ScopeError (expected):`);
      console.log(`  capability: ${e.capability}`);
      console.log(`  required:   ${JSON.stringify(e.required)}`);
      console.log(`  granted:    ${JSON.stringify(e.granted)}`);
    }
  }
}

// ══════════════════════════════════════════════════════════════
// 5. REVOCATION
// ══════════════════════════════════════════════════════════════

async function runRevocationTest(): Promise<void> {
  console.log("\n=== Revocation ===");

  const task = createTask({ type: "analyze", params: {} }, {
    constraints: { budget_credits: 100, max_delegations: 5, allowed_capabilities: [], denied_capabilities: [] },
  });

  const token = signDelegation({
    issuerPrivateKey: orchestrator["_privateKey"],
    issuerDid: orchestrator.did,
    subjectDid: analyzer.did,
    scope: ["invoke:analyze", "read:db"],
    ttlSeconds: 3600,
  });
  task.auth_chain.push(token);

  // Works before revocation
  const resultBefore = await analyzer.handle({ ...task, auth_chain: [...task.auth_chain] });
  console.log(`Before revocation: row_count=${resultBefore.row_count}`);

  // Extract JTI and revoke
  const jti = (decodeJwtClaims(token) as { jti: string }).jti;
  revocationRegistry.revoke(jti);
  console.log(`Revoked token: ${jti}`);

  // Verify fails after revocation
  const okAfter = verifyAuthChain({
    chain: task.auth_chain,
    expectedSubject: analyzer.did,
    knownPublicKeys: new Map([[orchestrator.did, orchestrator.publicKey]]),
    revocationRegistry,
  });
  console.log(`Chain valid after revocation: ${okAfter}`);  // false
}

// ══════════════════════════════════════════════════════════════
// 6. DID ROUND-TRIP
// ══════════════════════════════════════════════════════════════

function runDidTest(): void {
  console.log("\n=== DID Round-trip ===");
  const pubKey = parseDid(orchestrator.did);
  const recovered = Array.from(pubKey).every((b, i) => b === orchestrator.publicKey[i]);
  console.log(`Public key recovered from DID: ${recovered}`);  // true
}

// ══════════════════════════════════════════════════════════════
// 7. MAIN
// ══════════════════════════════════════════════════════════════

await runHappyPath();
await runScopeTest();
await runRevocationTest();
runDidTest();

console.log("\n=== All tests passed ===");
```

---

## Step 9: Using AgentPassport with Hono (edge/serverless)

For edge runtimes (Cloudflare Workers, Deno Deploy, Bun) use Hono:

```typescript
// step9-hono-worker.ts
// Run with: bun run step9-hono-worker.ts  OR  wrangler dev

import { Hono } from "hono";
import { Agent, ScopeError } from "@agentpassport/core";
import type { TaskEnvelope } from "@agentpassport/core";

const agent = new Agent("edge-worker");

agent.capability(
  "transform",
  { requires: ["transform:data"] },
  async (task) => {
    const input = (task.intent.params.input as string) ?? "";
    return { output: input.split("").reverse().join(""), agent: agent.did };
  }
);

// Register trusted orchestrators from environment
// (In Cloudflare Workers: use wrangler.toml [vars])
const TRUSTED_DID = (typeof process !== "undefined" && process.env.TRUSTED_DID) ?? "";
const TRUSTED_PUB = (typeof process !== "undefined" && process.env.TRUSTED_PUB_HEX) ?? "";
if (TRUSTED_DID && TRUSTED_PUB) {
  agent.trustKeys({
    [TRUSTED_DID]: new Uint8Array(Buffer.from(TRUSTED_PUB, "hex")),
  });
}

const app = new Hono();

app.post("/agentpassport/tasks", async (c) => {
  let task: TaskEnvelope;
  try {
    task = await c.req.json<TaskEnvelope>();
  } catch {
    return c.json({ error: "invalid_json" }, 400);
  }

  try {
    const result = await agent.handle(task);
    return c.json(result);
  } catch (e) {
    if (e instanceof ScopeError) return c.json({ error: "scope_denied", message: e.message }, 403);
    if (e instanceof Error && e.message.startsWith("No handler")) {
      return c.json({ error: "unknown_capability" }, 404);
    }
    return c.json({ error: "internal_error" }, 500);
  }
});

app.get("/agent-card", (c) =>
  c.json({ did: agent.did, name: "edge-worker", endpoint: "https://my-worker.example.com" })
);

export default app;
```

---

## Step 10: Persist and restore agent identity

In production, you never want a new DID on every restart. Here's how to persist the keypair:

```typescript
// step10-persistent-identity.ts

import { generateKeypair, keypairFromSeed, Agent } from "@agentpassport/core";
import { readFileSync, writeFileSync, existsSync } from "fs";

const KEY_PATH = "./agent.seed";

function loadOrCreateKeypair(): { seed: Uint8Array } {
  if (existsSync(KEY_PATH)) {
    const seed = new Uint8Array(readFileSync(KEY_PATH));
    console.log("Loaded existing keypair from disk.");
    return { seed };
  } else {
    const { privateKey } = generateKeypair();
    const seed = privateKey.slice(0, 32);
    writeFileSync(KEY_PATH, seed);
    console.log("Generated new keypair and saved to disk.");
    return { seed };
  }
}

const { seed } = loadOrCreateKeypair();
const kp = keypairFromSeed(seed);
const agent = new Agent("persistent-worker", { privateKey: kp.privateKey });

console.log(`Agent DID (stable across restarts): ${agent.did}`);
// This DID will be the same every time as long as agent.seed exists.

// Share agent.did and agent.publicKey with orchestrators.
// Never share the seed or private key.
console.log(`Public key (hex): ${Buffer.from(agent.publicKey).toString("hex")}`);
```
