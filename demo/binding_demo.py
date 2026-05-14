"""
demo/binding_demo.py — agentpassport Ownership Binding Demo

Demonstrates:
  1. Generate agent identity (DID + keypair)
  2. Create a domain binding
  3. Create a wallet binding
  4. Assemble and inspect the binding document
  5. Verify signatures offline
  6. Revoke a wallet binding
  7. Show revocation status

Run with:
    uv run python -m demo.binding_demo
"""

from __future__ import annotations

import time

from agentpassport import (
    Binding,
    BindingDocument,
    bind_domain,
    bind_wallet,
    did_from_public_key,
    generate_keypair,
    revoke_wallet,
    verify_binding_attestation,
)

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

W = 60


def rule() -> None:
    print("━" * W)


def header(text: str) -> None:
    rule()
    print(f"  {text}")
    rule()


def step(n: int, text: str) -> None:
    print(f"\n[STEP {n}] {text}")


def ok(text: str) -> None:
    print(f"  ✅  {text}")


def info(label: str, value: str) -> None:
    print(f"  {label:<18} {value}")


def fail(text: str) -> None:
    print(f"  ❌  {text}")


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def main() -> None:
    header("agentpassport — Ownership Binding Demo")

    # ── Step 1: Generate identity ──────────────────────────────────────────

    step(1, "Generate agent identity")

    priv, pub = generate_keypair()
    did = did_from_public_key(pub)

    info("DID:", did[:40] + "…")
    info("Public key (hex):", pub.hex()[:40] + "…")
    ok("Agent identity created")

    # ── Step 2: Domain binding ─────────────────────────────────────────────

    step(2, "Bind agent to domain 'rufus.dev'")

    domain_binding = bind_domain(priv[:32], did, "rufus.dev")

    info("Type:", domain_binding.type)
    info("Claim:", str(domain_binding.claim))
    info("Issued at:", str(domain_binding.issued_at))
    info("Expires at:", str(domain_binding.expires_at))
    info("Signature:", domain_binding.signature_hex[:40] + "…")
    ok("Domain binding created")

    # ── Step 3: Wallet binding ─────────────────────────────────────────────

    step(3, "Bind agent to Ethereum wallet")

    eth_address = "0x" + "a" * 40  # example address
    wallet_binding = bind_wallet(priv[:32], did, "ethereum", eth_address)

    info("Type:", wallet_binding.type)
    info("Chain:", wallet_binding.claim["chain"])
    info("Address:", wallet_binding.claim["address"][:20] + "…")
    ok("Wallet binding created")

    # ── Step 4: Assemble document ──────────────────────────────────────────

    step(4, "Assemble binding document")

    doc = BindingDocument(version="1")
    doc.add(domain_binding)
    doc.add(wallet_binding)

    print()
    print("  Document (publish at https://rufus.dev/.well-known/agent-passport.json):")
    print()
    for line in doc.to_json().splitlines():
        print(f"    {line}")

    # ── Step 5: Offline verification ───────────────────────────────────────

    step(5, "Verify signatures offline")

    domain_ok = verify_binding_attestation(domain_binding)
    wallet_ok = verify_binding_attestation(wallet_binding)

    if domain_ok:
        ok("Domain binding signature valid")
    else:
        fail("Domain binding signature invalid")

    if wallet_ok:
        ok("Wallet binding signature valid")
    else:
        fail("Wallet binding signature invalid")

    # Tampered signature should fail
    tampered = Binding(
        type=domain_binding.type,
        agent_did=domain_binding.agent_did,
        claim=domain_binding.claim,
        issued_at=domain_binding.issued_at,
        expires_at=domain_binding.expires_at,
        signature_hex="ff" * 64,
    )
    tampered_ok = verify_binding_attestation(tampered)
    if not tampered_ok:
        ok("Tampered signature correctly rejected")
    else:
        fail("Tampered signature was NOT rejected (unexpected)")

    # Expired binding should fail
    expired_binding = bind_domain(
        priv[:32], did, "rufus.dev", expires_at=int(time.time()) - 1
    )
    expired_ok = verify_binding_attestation(expired_binding)
    if not expired_ok:
        ok("Expired binding correctly rejected")
    else:
        fail("Expired binding was NOT rejected (unexpected)")

    # ── Step 6: Revoke wallet binding ──────────────────────────────────────

    step(6, "Revoke wallet binding")

    revocation = revoke_wallet(priv[:32], did, "ethereum", eth_address)
    doc.revoke(revocation)

    info("Revoked at:", str(revocation.revoked_at))
    info("Signature:", revocation.signature_hex[:40] + "…")

    if doc.is_revoked(wallet_binding):
        ok("Wallet binding is now revoked")
    else:
        fail("Wallet binding revocation not detected (unexpected)")

    # Domain binding should be unaffected
    if not doc.is_revoked(domain_binding):
        ok("Domain binding unaffected by wallet revocation")
    else:
        fail("Domain binding incorrectly marked as revoked")

    # ── Step 7: Final document state ───────────────────────────────────────

    step(7, "Final document state")

    print()
    for b in doc.bindings:
        revoked = doc.is_revoked(b)
        expired = b.is_expired()
        status = " [REVOKED]" if revoked else (" [EXPIRED]" if expired else " [active]")
        print(f"  binding  type={b.type}{status}")
        print(f"           claim={b.claim}")

    print()
    for r in doc.revocations:
        print(f"  revocation  type={r.type}")
        print(f"              claim={r.claim}")

    # ── Done ───────────────────────────────────────────────────────────────

    print()
    rule()
    print()
    print("  To publish and verify against a real domain:")
    print()
    print("    agentpass identity keygen --alias myagent")
    print("    agentpass identity bind-domain "
          "--alias myagent --domain example.com --output ap.json")
    print("    agentpass identity bind-wallet "
          "--alias myagent --chain ethereum --address 0x... --output ap.json")
    print()
    print("    # publish ap.json at https://example.com/.well-known/agent-passport.json")
    print()
    print("    agentpass identity verify-domain --did <DID> --domain example.com")
    print("    agentpass identity verify-wallet "
          "--did <DID> --chain ethereum --address 0x... --domain example.com")
    print()
    rule()


if __name__ == "__main__":
    main()
