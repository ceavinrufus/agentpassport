// identity.ts
// DID generation, Ed25519 keypair, base58btc — wire-compatible with Python SDK

import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha512";

// @noble/ed25519 v2+ requires an explicit SHA-512 implementation
ed.etc.sha512Sync = (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));

// Base58btc alphabet — identical to Python SDK
const BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

// Multicodec prefix for Ed25519 public key: varint-encoded 0xed01
const ED25519_PREFIX = Uint8Array.from([0xed, 0x01]);

// ---------------------------------------------------------------------------
// Base58btc (pure — no external dep)
// ---------------------------------------------------------------------------

export function base58btcEncode(data: Uint8Array): string {
  let leadingZeros = 0;
  for (const b of data) {
    if (b !== 0) break;
    leadingZeros++;
  }

  let n = 0n;
  for (const b of data) {
    n = n * 256n + BigInt(b);
  }

  const digits: string[] = [];
  while (n > 0n) {
    const rem = Number(n % 58n);
    n /= 58n;
    digits.push(BASE58_ALPHABET[rem]);
  }

  return "1".repeat(leadingZeros) + digits.reverse().join("");
}

export function base58btcDecode(s: string): Uint8Array {
  let leadingZeros = 0;
  for (const c of s) {
    if (c !== "1") break;
    leadingZeros++;
  }

  let n = 0n;
  for (const c of s) {
    const idx = BASE58_ALPHABET.indexOf(c);
    if (idx < 0) throw new Error(`Invalid base58btc character: ${c}`);
    n = n * 58n + BigInt(idx);
  }

  const bytes: number[] = [];
  while (n > 0n) {
    bytes.push(Number(n % 256n));
    n /= 256n;
  }

  const result = new Uint8Array(leadingZeros + bytes.length);
  for (let i = 0; i < bytes.length; i++) {
    result[leadingZeros + i] = bytes[bytes.length - 1 - i];
  }
  return result;
}

// ---------------------------------------------------------------------------
// Keypair
// ---------------------------------------------------------------------------

export interface Keypair {
  /** 64-byte seed+pubkey — matches Python: bytes(sk) + bytes(sk.verify_key) */
  privateKey: Uint8Array;
  /** 32-byte Ed25519 public key */
  publicKey: Uint8Array;
}

export function generateKeypair(): Keypair {
  const seed = ed.utils.randomPrivateKey(); // 32-byte seed
  const publicKey = ed.getPublicKey(seed);
  // Mirror Python layout: 64 bytes = seed (32) + pubkey (32)
  const privateKey = new Uint8Array(64);
  privateKey.set(seed);
  privateKey.set(publicKey, 32);
  return { privateKey, publicKey };
}

/** Build a Keypair from a raw 32-byte seed (useful in tests). */
export function keypairFromSeed(seed: Uint8Array): Keypair {
  if (seed.length !== 32) throw new Error("Seed must be 32 bytes");
  const publicKey = ed.getPublicKey(seed);
  const privateKey = new Uint8Array(64);
  privateKey.set(seed);
  privateKey.set(publicKey, 32);
  return { privateKey, publicKey };
}

// ---------------------------------------------------------------------------
// DID
// ---------------------------------------------------------------------------

export function didFromPublicKey(publicKey: Uint8Array): string {
  const prefixed = new Uint8Array(ED25519_PREFIX.length + publicKey.length);
  prefixed.set(ED25519_PREFIX);
  prefixed.set(publicKey, ED25519_PREFIX.length);
  return `did:key:z${base58btcEncode(prefixed)}`;
}

export function parseDid(did: string): Uint8Array {
  if (!did.startsWith("did:key:z")) {
    throw new Error(`Invalid did:key DID (expected did:key:z...): ${did}`);
  }
  const encoded = did.slice(9); // strip "did:key:z"
  const prefixed = base58btcDecode(encoded);
  if (prefixed[0] !== 0xed || prefixed[1] !== 0x01) {
    throw new Error(
      `DID does not contain an Ed25519 key (expected 0xed01 multicodec prefix): ${did}`
    );
  }
  return prefixed.slice(2); // strip 2-byte multicodec prefix
}
