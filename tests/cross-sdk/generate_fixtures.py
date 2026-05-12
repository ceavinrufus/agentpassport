"""
generate_fixtures.py — Python side of cross-SDK wire-compatibility fixtures.

Generates DIDs, signs delegation JWTs, builds multi-hop chains, and writes
everything to fixtures.json for consumption by the TypeScript test suite.

Run from the repo root:
    PATH=/root/.local/bin:$PATH uv run python tests/cross-sdk/generate_fixtures.py
"""

from __future__ import annotations

import json
import sys
import os

# Ensure the Python SDK is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../packages/aps-sdk/src"))

from aps_sdk.identity.did import generate_keypair, did_from_public_key
from aps_sdk.identity.signing import sign_delegation


def _hex(b: bytes) -> str:
    return b.hex()


def make_party() -> dict:
    private_key, public_key = generate_keypair()
    did = did_from_public_key(public_key)
    return {
        "private_key": private_key,
        "public_key": public_key,
        "did": did,
    }


def tamper_token(token: str) -> str:
    """Flip a byte in the signature part (part[2]) of a JWT."""
    parts = token.split(".")
    sig = bytearray(parts[2].encode())
    # Flip the last character by one ASCII value (stay in base64url range)
    sig[-1] = sig[-1] ^ 0x01
    parts[2] = sig.decode()
    return ".".join(parts)


def main() -> None:
    out_path = os.path.join(os.path.dirname(__file__), "fixtures.json")

    # -----------------------------------------------------------------------
    # Scenario 1 & 5: single-hop delegation
    # -----------------------------------------------------------------------
    issuer = make_party()
    subject = make_party()

    single_hop_token = sign_delegation(
        issuer_private_key=issuer["private_key"],
        issuer_did=issuer["did"],
        subject_did=subject["did"],
        scope=["read:db:customers"],
        ttl_seconds=86400,
    )

    # -----------------------------------------------------------------------
    # Scenario 3: 3-hop chain  root → hop1 → hop2 → leaf
    # -----------------------------------------------------------------------
    root = make_party()
    hop1 = make_party()
    hop2 = make_party()
    leaf = make_party()

    chain_token_1 = sign_delegation(
        issuer_private_key=root["private_key"],
        issuer_did=root["did"],
        subject_did=hop1["did"],
        scope=["read:db:customers", "write:api:stripe"],
        ttl_seconds=86400,
    )
    chain_token_2 = sign_delegation(
        issuer_private_key=hop1["private_key"],
        issuer_did=hop1["did"],
        subject_did=hop2["did"],
        scope=["read:db:customers", "write:api:stripe"],
        ttl_seconds=86400,
    )
    chain_token_3 = sign_delegation(
        issuer_private_key=hop2["private_key"],
        issuer_did=hop2["did"],
        subject_did=leaf["did"],
        scope=["read:db:customers"],
        ttl_seconds=86400,
    )

    fixtures = {
        "generated_by": "python",
        "single_hop": {
            "issuer_did": issuer["did"],
            "issuer_public_key_hex": _hex(issuer["public_key"]),
            "subject_did": subject["did"],
            "subject_public_key_hex": _hex(subject["public_key"]),
            "token": single_hop_token,
            "scope": ["read:db:customers"],
        },
        "three_hop_chain": {
            "parties": [
                {"did": root["did"],  "public_key_hex": _hex(root["public_key"])},
                {"did": hop1["did"],  "public_key_hex": _hex(hop1["public_key"])},
                {"did": hop2["did"],  "public_key_hex": _hex(hop2["public_key"])},
                {"did": leaf["did"],  "public_key_hex": _hex(leaf["public_key"])},
            ],
            "chain": [chain_token_1, chain_token_2, chain_token_3],
            "expected_subject_did": leaf["did"],
        },
        "tampered_token": {
            "issuer_did": issuer["did"],
            "issuer_public_key_hex": _hex(issuer["public_key"]),
            "subject_did": subject["did"],
            "token": tamper_token(single_hop_token),
        },
    }

    with open(out_path, "w") as f:
        json.dump(fixtures, f, indent=2)

    print(f"Written: {out_path}")
    print(f"  single_hop issuer:  {issuer['did'][:40]}...")
    print(f"  single_hop subject: {subject['did'][:40]}...")
    print(f"  3-hop chain: {len(fixtures['three_hop_chain']['chain'])} tokens, leaf={leaf['did'][:40]}...")


if __name__ == "__main__":
    main()
