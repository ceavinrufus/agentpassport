"""agentpassport.identity.binding — Ownership binding for agent DIDs.

Allows an agent DID to be cryptographically linked to a real-world anchor:
- Domain binding: prove a domain controls this DID via /.well-known/agent-passport.json
- Wallet binding: prove a blockchain address is linked to this DID (coming soon)

The attestation is signed by the agent's private key. Anyone can verify it
offline using the agent's public key (derivable from the DID itself).

Published format (/.well-known/agent-passport.json):

    {
      "version": "1",
      "bindings": [
        {
          "type": "domain",
          "agent_did": "did:key:z6Mk...",
          "claim": { "domain": "rufus.dev" },
          "issued_at": 1778716471,
          "expires_at": null,
          "signature": "<ed25519 hex>"
        }
      ]
    }

Multiple bindings (domain + wallet) can coexist in the same file.
Revocation: remove the entry from the array (domain) or publish a revocation
attestation (wallet, coming soon).

No central registry. No chain calls. Just crypto + DNS.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from agentpassport.identity.did import parse_did

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BINDING_VERSION = "1"
BINDING_TYPE_DOMAIN = "domain"
BINDING_TYPE_WALLET = "wallet"

# Canonical signing payload prefix — prevents cross-protocol signature reuse
_SIGNING_PREFIX = b"agentpassport.binding.v1:"

# ---------------------------------------------------------------------------
# Binding dataclass
# ---------------------------------------------------------------------------


@dataclass
class Binding:
    """A signed attestation linking an agent DID to a real-world anchor.

    Attributes:
        type:          "domain" or "wallet"
        agent_did:     The agent's DID (did:key:z...)
        claim:         Dict with anchor-specific fields:
                         domain binding: {"domain": "rufus.dev"}
                         wallet binding: {"chain": "ethereum", "address": "0x..."}
        issued_at:     Unix timestamp of when the binding was created
        expires_at:    Optional Unix timestamp after which the binding is invalid.
                       None means no expiry.
        signature_hex: Ed25519 signature over the canonical payload (hex-encoded)
    """

    type: str
    agent_did: str
    claim: dict
    issued_at: int
    expires_at: int | None
    signature_hex: str

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "agent_did": self.agent_did,
            "claim": self.claim,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": self.signature_hex,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Binding:
        return cls(
            type=data["type"],
            agent_did=data["agent_did"],
            claim=data["claim"],
            issued_at=data["issued_at"],
            expires_at=data.get("expires_at"),
            signature_hex=data["signature"],
        )

    def is_expired(self) -> bool:
        """Return True if expires_at is set and has passed."""
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at


@dataclass
class BindingDocument:
    """The full /.well-known/agent-passport.json document.

    Contains a list of bindings — domain and/or wallet — for an agent.
    Multiple bindings of different types can coexist.
    """

    version: str
    bindings: list[Binding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "bindings": [b.to_dict() for b in self.bindings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> BindingDocument:
        return cls(
            version=data["version"],
            bindings=[Binding.from_dict(b) for b in data.get("bindings", [])],
        )

    def add(self, binding: Binding) -> None:
        """Add a binding to the document."""
        self.bindings.append(binding)

    def domain_bindings(self) -> list[Binding]:
        return [b for b in self.bindings if b.type == BINDING_TYPE_DOMAIN]

    def wallet_bindings(self) -> list[Binding]:
        return [b for b in self.bindings if b.type == BINDING_TYPE_WALLET]


# ---------------------------------------------------------------------------
# Canonical payload helpers
# ---------------------------------------------------------------------------

def _domain_payload(agent_did: str, domain: str, issued_at: int, expires_at: int | None) -> bytes:
    parts = "|".join([
        BINDING_VERSION,
        BINDING_TYPE_DOMAIN,
        agent_did,
        domain,
        str(issued_at),
        str(expires_at) if expires_at is not None else "null",
    ])
    return _SIGNING_PREFIX + parts.encode()


# ---------------------------------------------------------------------------
# Create bindings
# ---------------------------------------------------------------------------

def bind_domain(
    private_key: bytes,
    agent_did: str,
    domain: str,
    *,
    expires_at: int | None = None,
) -> Binding:
    """Create a signed domain binding attestation.

    Args:
        private_key: The agent's Ed25519 private key seed (32 bytes).
        agent_did:   The agent's DID (did:key:z...).
        domain:      The domain to bind to (e.g. "rufus.dev"). No scheme, no path.
        expires_at:  Optional Unix timestamp after which the binding expires.

    Returns:
        A Binding attestation. Add it to a BindingDocument and publish at
        https://{domain}/.well-known/agent-passport.json

    Example::

        priv, pub = generate_keypair()
        did = did_from_public_key(pub)
        binding = bind_domain(priv[:32], did, "rufus.dev")
        doc = BindingDocument(version="1")
        doc.add(binding)
        print(doc.to_json())
    """
    domain = domain.lower().strip().rstrip("/")
    if domain.startswith("http"):
        raise ValueError(
            "domain should not include scheme (e.g. use 'rufus.dev' not 'https://rufus.dev')"
        )

    issued_at = int(time.time())
    payload = _domain_payload(agent_did, domain, issued_at, expires_at)
    sk = SigningKey(private_key[:32])
    sig = sk.sign(payload).signature

    return Binding(
        type=BINDING_TYPE_DOMAIN,
        agent_did=agent_did,
        claim={"domain": domain},
        issued_at=issued_at,
        expires_at=expires_at,
        signature_hex=sig.hex(),
    )


# ---------------------------------------------------------------------------
# Verify binding (offline)
# ---------------------------------------------------------------------------

def verify_binding_attestation(binding: Binding) -> bool:
    """Verify a Binding attestation offline.

    Derives the public key from agent_did and verifies the signature.
    Also checks expiry if expires_at is set.
    Does NOT fetch anything from the network.

    Returns True if valid, False otherwise.
    """
    if binding.is_expired():
        return False

    try:
        pub_bytes = parse_did(binding.agent_did)
        vk = VerifyKey(pub_bytes)

        if binding.type == BINDING_TYPE_DOMAIN:
            domain = binding.claim.get("domain", "")
            payload = _domain_payload(
                binding.agent_did, domain, binding.issued_at, binding.expires_at
            )
        else:
            return False  # unknown type

        vk.verify(payload, bytes.fromhex(binding.signature_hex))
        return True
    except (BadSignatureError, ValueError, Exception):
        return False


# ---------------------------------------------------------------------------
# Verify domain binding (online — fetch from domain)
# ---------------------------------------------------------------------------

def verify_domain_binding(
    agent_did: str,
    domain: str,
    timeout: float = 5.0,
) -> bool:
    """Verify that a domain claims ownership of an agent DID.

    Fetches https://{domain}/.well-known/agent-passport.json and checks
    if any valid, non-expired domain binding exists for the given DID.

    Args:
        agent_did: The DID to verify ownership of.
        domain:    The domain to check (e.g. "rufus.dev").
        timeout:   HTTP request timeout in seconds.

    Returns:
        True if the domain publishes a valid binding for this DID.
        False if not found, invalid, expired, or signature mismatch.
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
        doc = BindingDocument.from_dict(data)
    except (KeyError, TypeError):
        return False

    for binding in doc.domain_bindings():
        if binding.agent_did != agent_did:
            continue
        if binding.claim.get("domain") != domain:
            continue
        if verify_binding_attestation(binding):
            return True

    return False


# ---------------------------------------------------------------------------
# Backwards compat aliases
# ---------------------------------------------------------------------------

# Old name kept for anyone already using it
def verify_domain_binding_attestation(binding: Binding) -> bool:
    """Alias for verify_binding_attestation. Prefer verify_binding_attestation."""
    return verify_binding_attestation(binding)
