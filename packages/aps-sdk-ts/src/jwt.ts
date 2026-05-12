// jwt.ts
// EdDSA JWT sign/verify and auth-chain verification — wire-compatible with Python SDK

import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha512";
import { parseDid } from "./identity.js";
import type { RevocationRegistry } from "./revocation.js";

ed.etc.sha512Sync = (...m: Uint8Array[]) => sha512(...m);

// ---------------------------------------------------------------------------
// Base64url helpers (no external dep)
// ---------------------------------------------------------------------------

function b64urlEncode(data: Uint8Array): string {
  // btoa works on binary strings
  let binary = "";
  for (let i = 0; i < data.length; i++) binary += String.fromCharCode(data[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): Uint8Array {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/");
  const padding = (4 - (padded.length % 4)) % 4;
  const base64 = padded + "=".repeat(padding);
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// ---------------------------------------------------------------------------
// JWT header (constant — same as Python)
// ---------------------------------------------------------------------------

const JWT_HEADER_OBJ = { alg: "EdDSA", crv: "Ed25519" };
const JWT_HEADER = b64urlEncode(
  new TextEncoder().encode(JSON.stringify(JWT_HEADER_OBJ))
);

// ---------------------------------------------------------------------------
// JWT claims types
// ---------------------------------------------------------------------------

export interface DelegationClaims {
  iss: string;
  sub: string;
  iat: number;
  exp: number;
  jti: string;
  scope: string[];
  max_delegations: number;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function encodeJwt(claims: Record<string, unknown>, seed: Uint8Array): string {
  // Sort keys — matches Python's sort_keys=True
  const sorted = Object.fromEntries(
    Object.keys(claims)
      .sort()
      .map((k) => [k, claims[k]])
  );
  const payload = b64urlEncode(
    new TextEncoder().encode(JSON.stringify(sorted))
  );
  const signingInput = new TextEncoder().encode(`${JWT_HEADER}.${payload}`);
  const sig = ed.sign(signingInput, seed);
  return `${JWT_HEADER}.${payload}.${b64urlEncode(sig)}`;
}

function decodeJwtClaims(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error(`Malformed JWT: expected 3 parts, got ${parts.length}`);
  return JSON.parse(new TextDecoder().decode(b64urlDecode(parts[1])));
}

function verifyJwtSignature(token: string, publicKeyBytes: Uint8Array): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error(`Malformed JWT: expected 3 parts, got ${parts.length}`);

  const header = JSON.parse(new TextDecoder().decode(b64urlDecode(parts[0])));
  if (header.alg !== "EdDSA") throw new Error(`Unsupported JWT algorithm: ${header.alg}`);

  const signingInput = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const sig = b64urlDecode(parts[2]);

  const valid = ed.verify(sig, signingInput, publicKeyBytes);
  if (!valid) throw new Error("Invalid JWT signature");

  return JSON.parse(new TextDecoder().decode(b64urlDecode(parts[1])));
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface SignDelegationOptions {
  issuerPrivateKey: Uint8Array; // 64-byte (seed+pubkey) or 32-byte seed
  issuerDid: string;
  subjectDid: string;
  scope: string[];
  ttlSeconds?: number;
  maxDelegations?: number;
}

export function signDelegation(opts: SignDelegationOptions): string {
  const {
    issuerPrivateKey,
    issuerDid,
    subjectDid,
    scope,
    ttlSeconds = 3600,
    maxDelegations = 0,
  } = opts;

  const now = Math.floor(Date.now() / 1000);
  const exp = now + ttlSeconds;
  const jti = crypto.randomUUID();

  const claims: Record<string, unknown> = {
    iss: issuerDid,
    sub: subjectDid,
    iat: now,
    exp,
    jti,
    scope,
    max_delegations: maxDelegations,
  };

  // First 32 bytes are the seed — matches Python: seed = private_key[:32]
  const seed = issuerPrivateKey.slice(0, 32);
  return encodeJwt(claims, seed);
}

export interface VerifyAuthChainOptions {
  chain: string[];
  expectedSubject: string;
  knownPublicKeys: Map<string, Uint8Array>;
  revocationRegistry?: RevocationRegistry;
}

export function verifyAuthChain(opts: VerifyAuthChainOptions): boolean {
  const { chain, expectedSubject, knownPublicKeys, revocationRegistry } = opts;

  if (chain.length === 0) return false;

  const nowTs = Date.now() / 1000;

  for (const token of chain) {
    // Decode unverified claims first to find the issuer
    let unverified: Record<string, unknown>;
    try {
      unverified = decodeJwtClaims(token);
    } catch {
      return false;
    }

    const issuer = unverified["iss"] as string | undefined;
    const pubKeyBytes = issuer ? knownPublicKeys.get(issuer) : undefined;
    if (!pubKeyBytes) return false;

    // Cryptographic verification
    let claims: Record<string, unknown>;
    try {
      claims = verifyJwtSignature(token, pubKeyBytes);
    } catch {
      return false;
    }

    // Temporal validity
    const iat = claims["iat"];
    const exp = claims["exp"];
    if (typeof iat !== "number" || typeof exp !== "number") return false;
    if (iat > nowTs || nowTs > exp) return false;

    // jti required
    const jti = claims["jti"];
    if (!jti || typeof jti !== "string") return false;

    // Revocation check
    if (revocationRegistry?.isRevoked(jti)) return false;
  }

  // Final subject check
  try {
    const lastClaims = decodeJwtClaims(chain[chain.length - 1]);
    return lastClaims["sub"] === expectedSubject;
  } catch {
    return false;
  }
}

/** Decode JWT claims without verifying (useful for inspection). */
export { decodeJwtClaims };
