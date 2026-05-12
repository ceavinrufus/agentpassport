import { describe, it, expect } from "vitest";
import {
  generateKeypair,
  keypairFromSeed,
  didFromPublicKey,
  parseDid,
  base58btcEncode,
  base58btcDecode,
} from "../src/identity.js";

describe("base58btc", () => {
  it("round-trips arbitrary bytes", () => {
    const data = new Uint8Array([0x00, 0x01, 0xde, 0xad, 0xbe, 0xef]);
    expect(base58btcDecode(base58btcEncode(data))).toEqual(data);
  });

  it("preserves leading zero bytes", () => {
    const data = new Uint8Array([0x00, 0x00, 0x01]);
    const encoded = base58btcEncode(data);
    expect(encoded.startsWith("11")).toBe(true);
    expect(base58btcDecode(encoded)).toEqual(data);
  });

  it("rejects invalid character", () => {
    expect(() => base58btcDecode("0OIl")).toThrow("Invalid base58btc character");
  });
});

describe("generateKeypair", () => {
  it("returns a 64-byte privateKey and 32-byte publicKey", () => {
    const kp = generateKeypair();
    expect(kp.privateKey).toHaveLength(64);
    expect(kp.publicKey).toHaveLength(32);
  });

  it("privateKey[32:64] equals publicKey", () => {
    const kp = generateKeypair();
    expect(kp.privateKey.slice(32)).toEqual(kp.publicKey);
  });

  it("generates distinct keypairs each call", () => {
    const a = generateKeypair();
    const b = generateKeypair();
    expect(a.publicKey).not.toEqual(b.publicKey);
  });
});

describe("keypairFromSeed", () => {
  it("derives same keypair from same seed", () => {
    const seed = new Uint8Array(32).fill(42);
    const a = keypairFromSeed(seed);
    const b = keypairFromSeed(seed);
    expect(a.publicKey).toEqual(b.publicKey);
  });

  it("rejects seed that is not 32 bytes", () => {
    expect(() => keypairFromSeed(new Uint8Array(16))).toThrow("Seed must be 32 bytes");
  });
});

describe("didFromPublicKey / parseDid", () => {
  it("produces a did:key:z... string", () => {
    const { publicKey } = generateKeypair();
    const did = didFromPublicKey(publicKey);
    expect(did).toMatch(/^did:key:z[1-9A-HJ-NP-Za-km-z]+$/);
  });

  it("round-trips public key through DID", () => {
    const { publicKey } = generateKeypair();
    const did = didFromPublicKey(publicKey);
    expect(parseDid(did)).toEqual(publicKey);
  });

  it("parseDid rejects non-did:key strings", () => {
    expect(() => parseDid("did:web:example.com")).toThrow("Invalid did:key DID");
  });

  it("parseDid rejects DID with wrong multicodec prefix", () => {
    // Manually craft a DID with wrong prefix (0x1200 instead of 0xed01)
    const fakeKey = new Uint8Array(34);
    fakeKey[0] = 0x12;
    fakeKey[1] = 0x00;
    const fakeDid = `did:key:z${base58btcEncode(fakeKey)}`;
    expect(() => parseDid(fakeDid)).toThrow("0xed01 multicodec prefix");
  });

  it("two distinct keypairs produce distinct DIDs", () => {
    const a = generateKeypair();
    const b = generateKeypair();
    expect(didFromPublicKey(a.publicKey)).not.toBe(didFromPublicKey(b.publicKey));
  });
});
