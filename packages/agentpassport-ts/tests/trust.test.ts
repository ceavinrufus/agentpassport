import { describe, it, expect } from "vitest";
import { TrustMiddleware, ScopeError } from "../src/trust.js";
import { signDelegation } from "../src/jwt.js";
import { generateKeypair, didFromPublicKey } from "../src/identity.js";

function makeParty() {
  const kp = generateKeypair();
  const did = didFromPublicKey(kp.publicKey);
  return { kp, did };
}

describe("TrustMiddleware", () => {
  it("passes when capability has no required scope", () => {
    const agent = makeParty();
    const middleware = new TrustMiddleware(
      agent.did,
      new Map(),
      new Map() // no scopes declared
    );
    // Should not throw
    expect(() => middleware.check([], "queryCustomers")).not.toThrow();
  });

  it("passes when auth chain grants the required scope", () => {
    const issuer = makeParty();
    const agent = makeParty();

    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: agent.did,
      scope: ["read:db:customers"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([[issuer.did, issuer.kp.publicKey]]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([token], "queryCustomers")).not.toThrow();
  });

  it("passes when auth chain grants wildcard *", () => {
    const issuer = makeParty();
    const agent = makeParty();

    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: agent.did,
      scope: ["*"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([[issuer.did, issuer.kp.publicKey]]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([token], "queryCustomers")).not.toThrow();
  });

  it("throws ScopeError when auth chain is empty but scope is required", () => {
    const agent = makeParty();
    const middleware = new TrustMiddleware(
      agent.did,
      new Map(),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([], "queryCustomers")).toThrow(ScopeError);
  });

  it("throws ScopeError when scope is missing from chain", () => {
    const issuer = makeParty();
    const agent = makeParty();

    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: agent.did,
      scope: ["write:api:stripe"], // wrong scope
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([[issuer.did, issuer.kp.publicKey]]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([token], "queryCustomers")).toThrow(ScopeError);
  });

  it("ScopeError carries capability name and required/granted info", () => {
    const agent = makeParty();
    const middleware = new TrustMiddleware(
      agent.did,
      new Map(),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    try {
      middleware.check([], "queryCustomers");
      expect.fail("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ScopeError);
      const err = e as ScopeError;
      expect(err.capability).toBe("queryCustomers");
      expect(err.required).toEqual(["read:db:customers"]);
    }
  });

  it("rejects a token addressed to a different agent", () => {
    const issuer = makeParty();
    const agent = makeParty();
    const other = makeParty();

    // Scope matches; the token is addressed to `other`, not `agent`.
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: other.did,
      scope: ["read:db:customers"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([[issuer.did, issuer.kp.publicKey]]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([token], "queryCustomers")).toThrow(ScopeError);
  });

  it("rejects a chain with an issuer/subject gap", () => {
    const root = makeParty();
    const skipped = makeParty();
    const other = makeParty();
    const agent = makeParty();

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: skipped.did,
      scope: ["read:db:customers"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: other.kp.privateKey,
      issuerDid: other.did,
      subjectDid: agent.did,
      scope: ["read:db:customers"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([
        [root.did, root.kp.publicKey],
        [other.did, other.kp.publicKey],
      ]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([hop1, hop2], "queryCustomers")).toThrow(ScopeError);
  });

  it("rejects a widened scope even when the required scope is on every hop", () => {
    const root = makeParty();
    const mid = makeParty();
    const agent = makeParty();

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: mid.did,
      scope: ["read:db:customers"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: mid.kp.privateKey,
      issuerDid: mid.did,
      subjectDid: agent.did,
      scope: ["read:db:customers", "write:db"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([
        [root.did, root.kp.publicKey],
        [mid.did, mid.kp.publicKey],
      ]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([hop1, hop2], "queryCustomers")).toThrow(ScopeError);
  });

  it("rejects a hop that introduces * without receiving it", () => {
    const root = makeParty();
    const mid = makeParty();
    const agent = makeParty();

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: mid.did,
      scope: ["read:db:customers"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: mid.kp.privateKey,
      issuerDid: mid.did,
      subjectDid: agent.did,
      scope: ["*"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([
        [root.did, root.kp.publicKey],
        [mid.did, mid.kp.publicKey],
      ]),
      new Map([["queryCustomers", ["admin"]]])
    );

    expect(() => middleware.check([hop1, hop2], "queryCustomers")).toThrow(ScopeError);
  });

  it("accepts a continuous chain whose scope only narrows", () => {
    const root = makeParty();
    const mid = makeParty();
    const agent = makeParty();

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: mid.did,
      scope: ["read:db:customers", "write:db"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: mid.kp.privateKey,
      issuerDid: mid.did,
      subjectDid: agent.did,
      scope: ["read:db:customers"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map([
        [root.did, root.kp.publicKey],
        [mid.did, mid.kp.publicKey],
      ]),
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([hop1, hop2], "queryCustomers")).not.toThrow();
  });

  it("ignores tokens from untrusted issuers", () => {
    const untrusted = makeParty();
    const agent = makeParty();

    const token = signDelegation({
      issuerPrivateKey: untrusted.kp.privateKey,
      issuerDid: untrusted.did,
      subjectDid: agent.did,
      scope: ["read:db:customers"],
    });

    const middleware = new TrustMiddleware(
      agent.did,
      new Map(), // untrusted not registered
      new Map([["queryCustomers", ["read:db:customers"]]])
    );

    expect(() => middleware.check([token], "queryCustomers")).toThrow(ScopeError);
  });
});
