import { describe, it, expect } from "vitest";
import { Agent, ScopeError } from "../src/agent.js";
import { generateKeypair, didFromPublicKey } from "../src/identity.js";
import { signDelegation } from "../src/jwt.js";
import { createTask } from "../src/types.js";

function makeParty() {
  const kp = generateKeypair();
  const did = didFromPublicKey(kp.publicKey);
  return { kp, did };
}

describe("Agent", () => {
  it("generates a DID on construction", () => {
    const agent = new Agent("test-agent");
    expect(agent.did).toMatch(/^did:key:z/);
  });

  it("two agents have distinct DIDs", () => {
    const a = new Agent("agent-a");
    const b = new Agent("agent-b");
    expect(a.did).not.toBe(b.did);
  });

  it("handles a task with no scope requirement", async () => {
    const agent = new Agent("agent");
    agent.capability("echo", {}, async (task) => ({
      echoed: task.intent.params,
    }));

    const task = createTask({ type: "echo", params: { msg: "hello" } });
    const result = await agent.handle(task);
    expect(result).toEqual({ echoed: { msg: "hello" } });
  });

  it("throws for unknown capability", async () => {
    const agent = new Agent("agent");
    const task = createTask({ type: "unknown", params: {} });
    await expect(agent.handle(task)).rejects.toThrow("No handler for capability: unknown");
  });

  it("passes scope check when auth chain grants required scope", async () => {
    const issuer = makeParty();
    const agent = new Agent("agent");

    agent.trustKeys({ [issuer.did]: issuer.kp.publicKey });

    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: agent.did,
      scope: ["read:db:customers"],
    });

    agent.capability(
      "queryCustomers",
      { requires: ["read:db:customers"] },
      async () => ({ ok: true })
    );

    const task = createTask(
      { type: "queryCustomers", params: {} },
      { auth_chain: [token] }
    );

    const result = await agent.handle(task);
    expect(result).toEqual({ ok: true });
  });

  it("throws ScopeError when scope is missing", async () => {
    const agent = new Agent("agent");
    agent.capability(
      "queryCustomers",
      { requires: ["read:db:customers"] },
      async () => ({ ok: true })
    );

    const task = createTask({ type: "queryCustomers", params: {} });
    await expect(agent.handle(task)).rejects.toThrow(ScopeError);
  });

  it("throws ScopeError for empty auth chain with required scope", async () => {
    const agent = new Agent("agent");
    agent.capability(
      "queryCustomers",
      { requires: ["read:db:customers"] },
      async () => ({ ok: true })
    );

    const task = createTask(
      { type: "queryCustomers", params: {} },
      { auth_chain: [] }
    );
    await expect(agent.handle(task)).rejects.toThrow(ScopeError);
  });

  it("delegate appends a JWT to the auth chain", () => {
    const agentA = new Agent("agent-a");
    const agentB = new Agent("agent-b");

    const task = createTask({ type: "echo", params: {} });
    expect(task.auth_chain).toHaveLength(0);

    const delegated = agentA.delegate(task, { targetDid: agentB.did });
    expect(delegated.auth_chain).toHaveLength(1);
    expect(delegated.state).toBe("delegated");
  });

  it("delegate preserves existing auth chain entries", () => {
    const agentA = new Agent("agent-a");
    const agentB = new Agent("agent-b");
    const agentC = new Agent("agent-c");

    const task = createTask({ type: "echo", params: {} });
    const step1 = agentA.delegate(task, { targetDid: agentB.did });
    const step2 = agentB.delegate(step1, { targetDid: agentC.did });

    expect(step2.auth_chain).toHaveLength(2);
  });

  it("trustKeys accepts a plain object", () => {
    const issuer = makeParty();
    const agent = new Agent("agent");
    // Should not throw
    expect(() =>
      agent.trustKeys({ [issuer.did]: issuer.kp.publicKey })
    ).not.toThrow();
  });

  it("trustKeys accepts a Map", () => {
    const issuer = makeParty();
    const agent = new Agent("agent");
    expect(() =>
      agent.trustKeys(new Map([[issuer.did, issuer.kp.publicKey]]))
    ).not.toThrow();
  });

  it("rejects a token addressed to a different agent", async () => {
    const issuer = makeParty();
    const other = makeParty();
    const agent = new Agent("agent");
    agent.trustKeys({ [issuer.did]: issuer.kp.publicKey });

    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: other.did,
      scope: ["read:db"],
    });

    let called = false;
    agent.capability("query", { requires: ["read:db"] }, async () => {
      called = true;
      return { ok: true };
    });

    const task = createTask({ type: "query", params: {} }, { auth_chain: [token] });
    await expect(agent.handle(task)).rejects.toThrow(ScopeError);
    expect(called).toBe(false);
  });

  it("rejects a chain with an issuer/subject gap", async () => {
    const root = makeParty();
    const skipped = makeParty();
    const other = makeParty();
    const agent = new Agent("agent");
    agent.trustKeys({
      [root.did]: root.kp.publicKey,
      [other.did]: other.kp.publicKey,
    });

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: skipped.did,
      scope: ["read:db"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: other.kp.privateKey,
      issuerDid: other.did,
      subjectDid: agent.did,
      scope: ["read:db"],
    });

    let called = false;
    agent.capability("query", { requires: ["read:db"] }, async () => {
      called = true;
      return { ok: true };
    });

    const task = createTask(
      { type: "query", params: {} },
      { auth_chain: [hop1, hop2] }
    );
    await expect(agent.handle(task)).rejects.toThrow(ScopeError);
    expect(called).toBe(false);
  });

  it("rejects a widened scope even when the required scope is on every hop", async () => {
    const root = makeParty();
    const mid = makeParty();
    const agent = new Agent("agent");
    agent.trustKeys({
      [root.did]: root.kp.publicKey,
      [mid.did]: mid.kp.publicKey,
    });

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: mid.did,
      scope: ["read:db"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: mid.kp.privateKey,
      issuerDid: mid.did,
      subjectDid: agent.did,
      scope: ["read:db", "write:db"],
    });

    let called = false;
    agent.capability("query", { requires: ["read:db"] }, async () => {
      called = true;
      return { ok: true };
    });

    const task = createTask(
      { type: "query", params: {} },
      { auth_chain: [hop1, hop2] }
    );
    await expect(agent.handle(task)).rejects.toThrow(ScopeError);
    expect(called).toBe(false);
  });

  it("accepts a continuous chain whose scope only narrows", async () => {
    const root = makeParty();
    const mid = makeParty();
    const agent = new Agent("agent");
    agent.trustKeys({
      [root.did]: root.kp.publicKey,
      [mid.did]: mid.kp.publicKey,
    });

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: mid.did,
      scope: ["read:db", "write:db"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: mid.kp.privateKey,
      issuerDid: mid.did,
      subjectDid: agent.did,
      scope: ["read:db"],
    });

    agent.capability("query", { requires: ["read:db"] }, async () => ({ rows: 1 }));

    const task = createTask(
      { type: "query", params: {} },
      { auth_chain: [hop1, hop2] }
    );
    await expect(agent.handle(task)).resolves.toEqual({ rows: 1 });
  });
});
