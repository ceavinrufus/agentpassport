/**
 * One signed delegation and a scope check.
 *
 * The orchestrator grants `read:records` to the worker. `read_record` runs.
 * `write_record` requires `write:records` and is rejected before its handler runs.
 *
 * No network access and no API keys.
 */

import { Agent, ScopeError, createTask, verifyAuthChain } from "@agentpassport/core";

const orchestrator = new Agent("orchestrator");
const worker = new Agent("worker");

worker.trustKeys({ [orchestrator.did]: orchestrator.publicKey });

worker.capability("read_record", { requires: ["read:records"] }, async (task) => {
  const id = task.intent.params.id;
  return { record: typeof id === "string" ? id : "", value: "stub" };
});

let writeHandlerRan = false;
worker.capability("write_record", { requires: ["write:records"] }, async () => {
  writeHandlerRan = true;
  return { written: true };
});

const readTask = orchestrator.delegate(
  createTask({ type: "read_record", params: { id: "42" } }),
  { targetDid: worker.did, scope: ["read:records"], ttlSeconds: 300 },
);

const chainOk = verifyAuthChain({
  chain: readTask.auth_chain,
  expectedSubject: worker.did,
  knownPublicKeys: new Map([[orchestrator.did, orchestrator.publicKey]]),
});
if (!chainOk || readTask.auth_chain.length !== 1) {
  throw new Error("delegation chain did not verify");
}

const allowed = await worker.handle(readTask);
if (allowed.record !== "42") {
  throw new Error(`unexpected read_record result: ${JSON.stringify(allowed)}`);
}

let denied: ScopeError | undefined;
try {
  await worker.handle(
    orchestrator.delegate(createTask({ type: "write_record", params: { id: "42" } }), {
      targetDid: worker.did,
      scope: ["read:records"],
      ttlSeconds: 300,
    }),
  );
} catch (err: unknown) {
  if (!(err instanceof ScopeError)) {
    throw err;
  }
  denied = err;
}

if (denied === undefined) {
  throw new Error("write_record should have been denied");
}
if (writeHandlerRan) {
  throw new Error("write_record handler ran without write:records");
}
if (!denied.message.includes("write:records")) {
  throw new Error(`scope error did not mention write:records: ${denied.message}`);
}

console.log("[orchestrator] signed delegation -> worker | scope: read:records");
console.log("chain verified");
console.log(`read_record -> ${JSON.stringify(allowed)}`);
console.log(`write_record denied: ${denied.message}`);
console.log("example ok");
