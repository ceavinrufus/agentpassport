/**
 * generate_ts_fixtures.ts — TypeScript side of cross-SDK wire-compatibility fixtures.
 *
 * Generates DIDs, signs delegation JWTs, builds multi-hop chains, and writes
 * everything to ts_fixtures.json for consumption by the Python test suite.
 *
 * Run from packages/aps-sdk-ts/:
 *   npx tsx ../../tests/cross-sdk/generate_ts_fixtures.ts
 */

import { writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

import { generateKeypair, didFromPublicKey } from "../../packages/aps-sdk-ts/src/identity.js";
import { signDelegation } from "../../packages/aps-sdk-ts/src/jwt.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function hex(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("hex");
}

function makeParty() {
  const kp = generateKeypair();
  const did = didFromPublicKey(kp.publicKey);
  return { kp, did };
}

function tamperToken(token: string): string {
  const parts = token.split(".");
  // Flip last byte of signature by XOR with 0x01 (on the raw base64url char)
  const sigBytes = Buffer.from(parts[2], "ascii");
  sigBytes[sigBytes.length - 1] ^= 0x01;
  parts[2] = sigBytes.toString("ascii");
  return parts.join(".");
}

// ---------------------------------------------------------------------------
// Scenario 1 & 5: single-hop delegation
// ---------------------------------------------------------------------------
const issuer = makeParty();
const subject = makeParty();

const singleHopToken = signDelegation({
  issuerPrivateKey: issuer.kp.privateKey,
  issuerDid: issuer.did,
  subjectDid: subject.did,
  scope: ["read:db:customers"],
  ttlSeconds: 86400,
});

// ---------------------------------------------------------------------------
// Scenario 4: 3-hop chain  root → hop1 → hop2 → leaf
// ---------------------------------------------------------------------------
const root = makeParty();
const hop1 = makeParty();
const hop2 = makeParty();
const leaf = makeParty();

const chainToken1 = signDelegation({
  issuerPrivateKey: root.kp.privateKey,
  issuerDid: root.did,
  subjectDid: hop1.did,
  scope: ["read:db:customers", "write:api:stripe"],
  ttlSeconds: 86400,
});
const chainToken2 = signDelegation({
  issuerPrivateKey: hop1.kp.privateKey,
  issuerDid: hop1.did,
  subjectDid: hop2.did,
  scope: ["read:db:customers", "write:api:stripe"],
  ttlSeconds: 86400,
});
const chainToken3 = signDelegation({
  issuerPrivateKey: hop2.kp.privateKey,
  issuerDid: hop2.did,
  subjectDid: leaf.did,
  scope: ["read:db:customers"],
  ttlSeconds: 86400,
});

const fixtures = {
  generated_by: "typescript",
  single_hop: {
    issuer_did: issuer.did,
    issuer_public_key_hex: hex(issuer.kp.publicKey),
    subject_did: subject.did,
    subject_public_key_hex: hex(subject.kp.publicKey),
    token: singleHopToken,
    scope: ["read:db:customers"],
  },
  three_hop_chain: {
    parties: [
      { did: root.did,  public_key_hex: hex(root.kp.publicKey) },
      { did: hop1.did,  public_key_hex: hex(hop1.kp.publicKey) },
      { did: hop2.did,  public_key_hex: hex(hop2.kp.publicKey) },
      { did: leaf.did,  public_key_hex: hex(leaf.kp.publicKey) },
    ],
    chain: [chainToken1, chainToken2, chainToken3],
    expected_subject_did: leaf.did,
  },
  tampered_token: {
    issuer_did: issuer.did,
    issuer_public_key_hex: hex(issuer.kp.publicKey),
    subject_did: subject.did,
    token: tamperToken(singleHopToken),
  },
};

const outPath = join(__dirname, "ts_fixtures.json");
writeFileSync(outPath, JSON.stringify(fixtures, null, 2));
console.log(`Written: ${outPath}`);
console.log(`  single_hop issuer:  ${issuer.did.slice(0, 40)}...`);
console.log(`  single_hop subject: ${subject.did.slice(0, 40)}...`);
console.log(`  3-hop chain: ${fixtures.three_hop_chain.chain.length} tokens, leaf=${leaf.did.slice(0, 40)}...`);
