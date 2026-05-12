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

  it("ignores tokens whose sub is not the agent DID", () => {
    const issuer = makeParty();
    const agent = makeParty();
    const other = makeParty();

    // Token delegates to 'other', not 'agent'
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
