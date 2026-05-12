import { describe, it, expect } from "vitest";
import {
  signDelegation,
  verifyAuthChain,
  decodeJwtClaims,
} from "../src/jwt.js";
import { generateKeypair, didFromPublicKey } from "../src/identity.js";
import { InMemoryRevocationRegistry } from "../src/revocation.js";

function makeParty() {
  const kp = generateKeypair();
  const did = didFromPublicKey(kp.publicKey);
  return { kp, did };
}

describe("signDelegation", () => {
  it("returns a 3-part JWT string", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
    });
    expect(token.split(".")).toHaveLength(3);
  });

  it("claims contain required fields", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["write:api:stripe"],
      maxDelegations: 2,
    });
    const claims = decodeJwtClaims(token);
    expect(claims["iss"]).toBe(issuer.did);
    expect(claims["sub"]).toBe(subject.did);
    expect(claims["scope"]).toEqual(["write:api:stripe"]);
    expect(claims["max_delegations"]).toBe(2);
    expect(typeof claims["jti"]).toBe("string");
    expect(typeof claims["iat"]).toBe("number");
    expect(typeof claims["exp"]).toBe("number");
  });

  it("exp = iat + ttlSeconds", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["*"],
      ttlSeconds: 7200,
    });
    const claims = decodeJwtClaims(token);
    expect((claims["exp"] as number) - (claims["iat"] as number)).toBe(7200);
  });
});

describe("verifyAuthChain", () => {
  it("returns true for a valid single-hop chain", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
    });
    const result = verifyAuthChain({
      chain: [token],
      expectedSubject: subject.did,
      knownPublicKeys: new Map([[issuer.did, issuer.kp.publicKey]]),
    });
    expect(result).toBe(true);
  });

  it("returns false for empty chain", () => {
    const subject = makeParty();
    expect(
      verifyAuthChain({
        chain: [],
        expectedSubject: subject.did,
        knownPublicKeys: new Map(),
      })
    ).toBe(false);
  });

  it("returns false when subject does not match", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const other = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
    });
    expect(
      verifyAuthChain({
        chain: [token],
        expectedSubject: other.did,
        knownPublicKeys: new Map([[issuer.did, issuer.kp.publicKey]]),
      })
    ).toBe(false);
  });

  it("returns false when issuer is not in known keys", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
    });
    expect(
      verifyAuthChain({
        chain: [token],
        expectedSubject: subject.did,
        knownPublicKeys: new Map(), // issuer not trusted
      })
    ).toBe(false);
  });

  it("returns false when signature is tampered", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
    });
    const parts = token.split(".");
    // Tamper the payload
    const tampered = `${parts[0]}.${parts[1]}AAAA.${parts[2]}`;
    expect(
      verifyAuthChain({
        chain: [tampered],
        expectedSubject: subject.did,
        knownPublicKeys: new Map([[issuer.did, issuer.kp.publicKey]]),
      })
    ).toBe(false);
  });

  it("returns false for an expired token", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
      ttlSeconds: -10, // already expired
    });
    expect(
      verifyAuthChain({
        chain: [token],
        expectedSubject: subject.did,
        knownPublicKeys: new Map([[issuer.did, issuer.kp.publicKey]]),
      })
    ).toBe(false);
  });

  it("returns false when jti is revoked", () => {
    const issuer = makeParty();
    const subject = makeParty();
    const token = signDelegation({
      issuerPrivateKey: issuer.kp.privateKey,
      issuerDid: issuer.did,
      subjectDid: subject.did,
      scope: ["read:db:customers"],
    });
    const claims = decodeJwtClaims(token);
    const registry = new InMemoryRevocationRegistry();
    registry.revoke(claims["jti"] as string);

    expect(
      verifyAuthChain({
        chain: [token],
        expectedSubject: subject.did,
        knownPublicKeys: new Map([[issuer.did, issuer.kp.publicKey]]),
        revocationRegistry: registry,
      })
    ).toBe(false);
  });

  it("verifies a two-hop chain", () => {
    const root = makeParty();
    const middle = makeParty();
    const leaf = makeParty();

    const hop1 = signDelegation({
      issuerPrivateKey: root.kp.privateKey,
      issuerDid: root.did,
      subjectDid: middle.did,
      scope: ["read:db:customers"],
    });
    const hop2 = signDelegation({
      issuerPrivateKey: middle.kp.privateKey,
      issuerDid: middle.did,
      subjectDid: leaf.did,
      scope: ["read:db:customers"],
    });

    expect(
      verifyAuthChain({
        chain: [hop1, hop2],
        expectedSubject: leaf.did,
        knownPublicKeys: new Map([
          [root.did, root.kp.publicKey],
          [middle.did, middle.kp.publicKey],
        ]),
      })
    ).toBe(true);
  });
});
