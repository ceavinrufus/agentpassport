from __future__ import annotations

import base64

from nacl.signing import SigningKey


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate an Ed25519 keypair. Returns (private_key_bytes, public_key_bytes)."""
    sk = SigningKey.generate()
    # Return seed + public key (64 bytes) to match Ed25519 convention
    return bytes(sk) + bytes(sk.verify_key), bytes(sk.verify_key)


def did_from_public_key(public_key: bytes) -> str:
    """Create a did:aps:<base64url-encoded-public-key> from raw public key bytes."""
    encoded = base64.urlsafe_b64encode(public_key).rstrip(b"=").decode("ascii")
    return f"did:aps:{encoded}"


def parse_did(did: str) -> bytes:
    """Extract public key bytes from a did:aps: string."""
    if not did.startswith("did:aps:"):
        raise ValueError(f"Invalid APS DID: {did}")
    encoded = did[8:]
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding
    return base64.urlsafe_b64decode(encoded)
