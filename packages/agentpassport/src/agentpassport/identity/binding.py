"""agentpassport.identity.binding — Ownership binding for agent DIDs.

Allows an agent DID to be cryptographically linked to a real-world anchor:
- Domain binding: prove a domain controls this DID via /.well-known/agent-passport.json
- Wallet binding: prove a blockchain address is linked to this DID

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
        },
        {
          "type": "wallet",
          "agent_did": "did:key:z6Mk...",
          "claim": { "chain": "ethereum", "address": "0x1234..." },
          "issued_at": 1778716471,
          "expires_at": null,
          "signature": "<ed25519 hex>"
        }
      ],
      "revocations": [
        {
          "type": "wallet",
          "agent_did": "did:key:z6Mk...",
          "claim": { "chain": "ethereum", "address": "0x1234..." },
          "revoked_at": 1778716999,
          "signature": "<ed25519 hex>"
        }
      ]
    }

Revocation: add a matching entry to `revocations` — verifier checks both arrays.
Domain binding is revoked by removing its entry from `bindings`.

No central registry. No chain calls. Just crypto + DNS.
"""

from __future__ import annotations

import json
import re
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
_REVOCATION_PREFIX = b"agentpassport.revocation.v1:"

# ---------------------------------------------------------------------------
# Address validation
# ---------------------------------------------------------------------------

# EVM-compatible chains (same address format)
_EVM_CHAINS = {
    "ethereum", "base", "polygon", "optimism", "arbitrum",
    "avalanche", "bnb", "gnosis", "zksync", "linea",
}

_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SOLANA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_BITCOIN_RE = re.compile(r"^(1|3|bc1)[a-zA-Z0-9]{25,62}$")


def validate_address(chain: str, address: str) -> None:
    """Validate address format for known chains.

    Raises ValueError if the address format is invalid for the given chain.
    For unknown chains, validation is skipped (lenient — don't block new chains).
    """
    chain = chain.lower()

    if chain in _EVM_CHAINS:
        if not _EVM_RE.match(address):
            raise ValueError(
                f"Invalid Ethereum-compatible address for chain '{chain}': '{address}'. "
                f"Expected 0x followed by 40 hex characters."
            )
    elif chain == "solana":
        if not _SOLANA_RE.match(address):
            raise ValueError(
                f"Invalid Solana address: '{address}'. "
                f"Expected base58-encoded string of 32–44 characters."
            )
    elif chain == "bitcoin" and not _BITCOIN_RE.match(address):
            raise ValueError(
                f"Invalid Bitcoin address: '{address}'. "
                f"Expected legacy (1...), P2SH (3...), or bech32 (bc1...) format."
            )
    # unknown chain — pass through


# ---------------------------------------------------------------------------
# Binding dataclass
# ---------------------------------------------------------------------------


@dataclass
class Binding:
    """A signed attestation linking an agent DID to a real-world anchor.

    Attributes:
        type:          "domain" or "wallet"
        agent_did:     The agent's DID (did:key:z...)
        claim:         Anchor-specific fields:
                         domain: {"domain": "rufus.dev"}
                         wallet: {"chain": "ethereum", "address": "0x..."}
        issued_at:     Unix timestamp of creation
        expires_at:    Optional expiry timestamp. None = no expiry.
        signature_hex: Ed25519 signature over canonical payload (hex)
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
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at


# ---------------------------------------------------------------------------
# Revocation dataclass
# ---------------------------------------------------------------------------


@dataclass
class Revocation:
    """A signed attestation revoking a wallet binding.

    Attributes:
        type:          Binding type being revoked ("wallet")
        agent_did:     The agent's DID
        claim:         Same claim as the binding being revoked
        revoked_at:    Unix timestamp of revocation
        signature_hex: Ed25519 signature over canonical revocation payload (hex)
    """

    type: str
    agent_did: str
    claim: dict
    revoked_at: int
    signature_hex: str

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "agent_did": self.agent_did,
            "claim": self.claim,
            "revoked_at": self.revoked_at,
            "signature": self.signature_hex,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Revocation:
        return cls(
            type=data["type"],
            agent_did=data["agent_did"],
            claim=data["claim"],
            revoked_at=data["revoked_at"],
            signature_hex=data["signature"],
        )


# ---------------------------------------------------------------------------
# BindingDocument
# ---------------------------------------------------------------------------


@dataclass
class BindingDocument:
    """The full /.well-known/agent-passport.json document.

    Contains bindings (domain + wallet) and revocations.
    """

    version: str
    bindings: list[Binding] = field(default_factory=list)
    revocations: list[Revocation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "bindings": [b.to_dict() for b in self.bindings],
            "revocations": [r.to_dict() for r in self.revocations],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> BindingDocument:
        return cls(
            version=data["version"],
            bindings=[Binding.from_dict(b) for b in data.get("bindings", [])],
            revocations=[Revocation.from_dict(r) for r in data.get("revocations", [])],
        )

    def add(self, binding: Binding) -> None:
        self.bindings.append(binding)

    def revoke(self, revocation: Revocation) -> None:
        self.revocations.append(revocation)

    def domain_bindings(self) -> list[Binding]:
        return [b for b in self.bindings if b.type == BINDING_TYPE_DOMAIN]

    def wallet_bindings(self) -> list[Binding]:
        return [b for b in self.bindings if b.type == BINDING_TYPE_WALLET]

    def is_revoked(self, binding: Binding) -> bool:
        """Return True if a matching revocation exists for this binding."""
        for r in self.revocations:
            if (
                r.type == binding.type
                and r.agent_did == binding.agent_did
                and r.claim == binding.claim
            ):
                return True
        return False


# ---------------------------------------------------------------------------
# Canonical payloads
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


def _wallet_payload(
    agent_did: str, chain: str, address: str, issued_at: int, expires_at: int | None
) -> bytes:
    parts = "|".join([
        BINDING_VERSION,
        BINDING_TYPE_WALLET,
        agent_did,
        chain,
        address,
        str(issued_at),
        str(expires_at) if expires_at is not None else "null",
    ])
    return _SIGNING_PREFIX + parts.encode()


def _revocation_payload(agent_did: str, chain: str, address: str, revoked_at: int) -> bytes:
    parts = "|".join([
        BINDING_VERSION,
        BINDING_TYPE_WALLET,
        agent_did,
        chain,
        address,
        str(revoked_at),
    ])
    return _REVOCATION_PREFIX + parts.encode()


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
        domain:      Domain to bind (e.g. "rufus.dev"). No scheme, no path.
        expires_at:  Optional Unix timestamp after which the binding expires.

    Returns:
        A Binding. Add it to a BindingDocument and publish at
        https://{domain}/.well-known/agent-passport.json
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


def bind_wallet(
    private_key: bytes,
    agent_did: str,
    chain: str,
    address: str,
    *,
    expires_at: int | None = None,
) -> Binding:
    """Create a signed wallet binding attestation.

    Args:
        private_key: The agent's Ed25519 private key seed (32 bytes).
        agent_did:   The agent's DID (did:key:z...).
        chain:       Chain identifier (e.g. "ethereum", "solana", "bitcoin").
        address:     Wallet address on the given chain.
        expires_at:  Optional Unix timestamp after which the binding expires.

    Returns:
        A Binding. Add it to a BindingDocument and publish at
        https://{domain}/.well-known/agent-passport.json

    Example::

        priv, pub = generate_keypair()
        did = did_from_public_key(pub)
        binding = bind_wallet(priv[:32], did, "ethereum", "0xAbc...123")
        doc = BindingDocument(version="1")
        doc.add(binding)
        print(doc.to_json())
    """
    chain = chain.lower().strip()
    validate_address(chain, address)

    issued_at = int(time.time())
    payload = _wallet_payload(agent_did, chain, address, issued_at, expires_at)
    sk = SigningKey(private_key[:32])
    sig = sk.sign(payload).signature

    return Binding(
        type=BINDING_TYPE_WALLET,
        agent_did=agent_did,
        claim={"chain": chain, "address": address},
        issued_at=issued_at,
        expires_at=expires_at,
        signature_hex=sig.hex(),
    )


def revoke_wallet(
    private_key: bytes,
    agent_did: str,
    chain: str,
    address: str,
) -> Revocation:
    """Create a signed wallet revocation attestation.

    Args:
        private_key: The agent's Ed25519 private key seed (32 bytes).
        agent_did:   The agent's DID.
        chain:       Chain identifier.
        address:     Wallet address to revoke.

    Returns:
        A Revocation. Add it to a BindingDocument via doc.revoke(r) and
        republish the document.
    """
    chain = chain.lower().strip()
    validate_address(chain, address)

    revoked_at = int(time.time())
    payload = _revocation_payload(agent_did, chain, address, revoked_at)
    sk = SigningKey(private_key[:32])
    sig = sk.sign(payload).signature

    return Revocation(
        type=BINDING_TYPE_WALLET,
        agent_did=agent_did,
        claim={"chain": chain, "address": address},
        revoked_at=revoked_at,
        signature_hex=sig.hex(),
    )


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_binding_attestation(binding: Binding) -> bool:
    """Verify a Binding attestation offline (no network, no revocation check).

    Checks signature validity and expiry. Does NOT check revocations —
    use verify_wallet_binding or verify_domain_binding for full verification.
    """
    if binding.is_expired():
        return False

    try:
        pub_bytes = parse_did(binding.agent_did)
        vk = VerifyKey(pub_bytes)

        if binding.type == BINDING_TYPE_DOMAIN:
            payload = _domain_payload(
                binding.agent_did,
                binding.claim["domain"],
                binding.issued_at,
                binding.expires_at,
            )
        elif binding.type == BINDING_TYPE_WALLET:
            payload = _wallet_payload(
                binding.agent_did,
                binding.claim["chain"],
                binding.claim["address"],
                binding.issued_at,
                binding.expires_at,
            )
        else:
            return False

        vk.verify(payload, bytes.fromhex(binding.signature_hex))
        return True
    except (BadSignatureError, ValueError, Exception):
        return False


def verify_revocation_attestation(revocation: Revocation) -> bool:
    """Verify a Revocation attestation signature offline."""
    try:
        pub_bytes = parse_did(revocation.agent_did)
        vk = VerifyKey(pub_bytes)
        payload = _revocation_payload(
            revocation.agent_did,
            revocation.claim["chain"],
            revocation.claim["address"],
            revocation.revoked_at,
        )
        vk.verify(payload, bytes.fromhex(revocation.signature_hex))
        return True
    except (BadSignatureError, ValueError, Exception):
        return False


def _fetch_binding_document(domain: str, timeout: float) -> BindingDocument | None:
    """Fetch and parse a BindingDocument from a domain's .well-known URL."""
    url = f"https://{domain}/.well-known/agent-passport.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agentpassport/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return BindingDocument.from_dict(data)
    except (urllib.error.URLError, json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def verify_domain_binding(
    agent_did: str,
    domain: str,
    timeout: float = 5.0,
) -> bool:
    """Verify that a domain claims ownership of an agent DID.

    Fetches https://{domain}/.well-known/agent-passport.json and checks
    if any valid, non-expired, non-revoked domain binding exists for the DID.
    """
    domain = domain.lower().strip().rstrip("/")
    doc = _fetch_binding_document(domain, timeout)
    if doc is None:
        return False

    for binding in doc.domain_bindings():
        if binding.agent_did != agent_did:
            continue
        if binding.claim.get("domain") != domain:
            continue
        if doc.is_revoked(binding):
            continue
        if verify_binding_attestation(binding):
            return True

    return False


def verify_wallet_binding(
    agent_did: str,
    chain: str,
    address: str,
    domain: str,
    timeout: float = 5.0,
) -> bool:
    """Verify that a wallet address is bound to an agent DID.

    Fetches https://{domain}/.well-known/agent-passport.json and checks
    if any valid, non-expired, non-revoked wallet binding exists for the
    given DID + chain + address combination.

    Args:
        agent_did: The DID to verify ownership of.
        chain:     Chain identifier (e.g. "ethereum").
        address:   Wallet address.
        domain:    Domain hosting the /.well-known/agent-passport.json file.
        timeout:   HTTP request timeout in seconds.
    """
    chain = chain.lower().strip()
    domain = domain.lower().strip().rstrip("/")
    doc = _fetch_binding_document(domain, timeout)
    if doc is None:
        return False

    for binding in doc.wallet_bindings():
        if binding.agent_did != agent_did:
            continue
        if binding.claim.get("chain") != chain:
            continue
        if binding.claim.get("address") != address:
            continue
        if doc.is_revoked(binding):
            continue
        if verify_binding_attestation(binding):
            return True

    return False


# ---------------------------------------------------------------------------
# Backwards compat alias
# ---------------------------------------------------------------------------

def verify_domain_binding_attestation(binding: Binding) -> bool:
    """Alias for verify_binding_attestation. Prefer verify_binding_attestation."""
    return verify_binding_attestation(binding)
