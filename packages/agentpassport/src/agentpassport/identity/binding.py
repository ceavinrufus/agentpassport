"""agentpassport.identity.binding — Ownership binding for agent DIDs.

Allows an agent DID to be cryptographically linked to a real-world anchor:
- Domain binding: prove a domain controls this DID via /.well-known/agent-passport.json
- Wallet binding: prove a blockchain address is linked to this DID (coming soon)

The attestation is signed by the agent's private key. Anyone can verify it
offline using the agent's public key (derivable from the DID itself).

Domain binding flow:
    1. Agent owner calls bind_domain() → gets a signed attestation
    2. Owner publishes attestation at https://{domain}/.well-known/agent-passport.json
    3. Anyone calls verify_domain_binding(did, domain) → fetches + verifies

No central registry. No chain calls. Just crypto + DNS.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from agentpassport.identity.did import parse_did

# ---------------------------------------------------------------------------
# Attestation format
# ---------------------------------------------------------------------------

BINDING_VERSION = "1"
BINDING_TYPE_DOMAIN = "domain"

# Canonical signing payload prefix — prevents cross-protocol signature reuse
_SIGNING_PREFIX = b"agentpassport.binding.v1:"


@dataclass
class DomainBinding:
    """A signed attestation linking an agent DID to a domain."""

    version: str
    type: str
    agent_did: str
    domain: str
    issued_at: int
    signature_hex: str

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "type": self.type,
            "agent_did": self.agent_did,
            "claim": {"domain": self.domain},
            "issued_at": self.issued_at,
            "signature": self.signature_hex,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DomainBinding:
        return cls(
            version=data["version"],
            type=data["type"],
            agent_did=data["agent_did"],
            domain=data["claim"]["domain"],
            issued_at=data["issued_at"],
            signature_hex=data["signature"],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Canonical payload
# ---------------------------------------------------------------------------

def _canonical_payload(agent_did: str, domain: str, issued_at: int) -> bytes:
    """Deterministic bytes that get signed. Order and content are fixed."""
    parts = "|".join([
        BINDING_VERSION,
        BINDING_TYPE_DOMAIN,
        agent_did,
        domain,
        str(issued_at),
    ])
    return _SIGNING_PREFIX + parts.encode()


# ---------------------------------------------------------------------------
# Create binding
# ---------------------------------------------------------------------------

def bind_domain(
    private_key: bytes,
    agent_did: str,
    domain: str,
) -> DomainBinding:
    """Create a signed domain binding attestation.

    Args:
        private_key: The agent's Ed25519 private key seed (32 bytes).
        agent_did:   The agent's DID (did:key:z...).
        domain:      The domain to bind to (e.g. "rufus.dev"). No scheme, no path.

    Returns:
        A DomainBinding attestation ready to be published at
        https://{domain}/.well-known/agent-passport.json

    Example::

        priv, pub = generate_keypair()
        did = did_from_public_key(pub)
        binding = bind_domain(priv[:32], did, "rufus.dev")
        print(binding.to_json())
    """
    domain = domain.lower().strip().rstrip("/")
    if domain.startswith("http"):
        raise ValueError("domain should not include scheme (e.g. use 'rufus.dev' not 'https://rufus.dev')")

    issued_at = int(time.time())
    payload = _canonical_payload(agent_did, domain, issued_at)

    sk = SigningKey(private_key[:32])
    sig = sk.sign(payload).signature

    return DomainBinding(
        version=BINDING_VERSION,
        type=BINDING_TYPE_DOMAIN,
        agent_did=agent_did,
        domain=domain,
        issued_at=issued_at,
        signature_hex=sig.hex(),
    )


# ---------------------------------------------------------------------------
# Verify binding (offline)
# ---------------------------------------------------------------------------

def verify_domain_binding_attestation(binding: DomainBinding) -> bool:
    """Verify a DomainBinding attestation offline.

    Derives the public key from the agent_did and verifies the signature.
    Does NOT fetch anything from the network.

    Returns True if the signature is valid, False otherwise.
    """
    try:
        pub_bytes = parse_did(binding.agent_did)
        payload = _canonical_payload(binding.agent_did, binding.domain, binding.issued_at)
        vk = VerifyKey(pub_bytes)
        vk.verify(payload, bytes.fromhex(binding.signature_hex))
        return True
    except (BadSignatureError, ValueError, Exception):
        return False


# ---------------------------------------------------------------------------
# Verify binding (online — fetch from domain)
# ---------------------------------------------------------------------------

def verify_domain_binding(
    agent_did: str,
    domain: str,
    timeout: float = 5.0,
) -> bool:
    """Verify that a domain claims ownership of an agent DID.

    Fetches https://{domain}/.well-known/agent-passport.json and verifies
    the attestation signature.

    Args:
        agent_did: The DID to verify ownership of.
        domain:    The domain to check (e.g. "rufus.dev").
        timeout:   HTTP request timeout in seconds.

    Returns:
        True if the domain publishes a valid binding for this DID.
        False if not found, invalid, or signature mismatch.
    """
    domain = domain.lower().strip().rstrip("/")
    url = f"https://{domain}/.well-known/agent-passport.json"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agentpassport/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return False

    try:
        binding = DomainBinding.from_dict(data)
    except (KeyError, TypeError):
        return False

    if binding.agent_did != agent_did:
        return False

    if binding.domain != domain:
        return False

    return verify_domain_binding_attestation(binding)
