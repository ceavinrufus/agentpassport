from __future__ import annotations

from nacl.signing import SigningKey

# Base58btc alphabet (Bitcoin/IPFS/W3C multibase standard)
_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# Multicodec prefix for Ed25519 public key: varint-encoded 0xed01
_ED25519_MULTICODEC_PREFIX = bytes([0xED, 0x01])


def _base58btc_encode(data: bytes) -> str:
    """Encode bytes using base58btc alphabet (no external dependency)."""
    n = int.from_bytes(data, "big")
    result = []
    while n:
        n, r = divmod(n, 58)
        result.append(_BASE58_ALPHABET[r])
    for byte in data:
        if byte == 0:
            result.append(_BASE58_ALPHABET[0])
        else:
            break
    return bytes(reversed(result)).decode("ascii")


def _base58btc_decode(s: str) -> bytes:
    """Decode a base58btc string to bytes."""
    n = 0
    for char in s.encode("ascii"):
        n = n * 58 + _BASE58_ALPHABET.index(char)
    result = []
    while n:
        n, r = divmod(n, 256)
        result.append(r)
    for char in s.encode("ascii"):
        if char == _BASE58_ALPHABET[0]:
            result.append(0)
        else:
            break
    return bytes(reversed(result))


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate an Ed25519 keypair. Returns (private_key_bytes, public_key_bytes)."""
    sk = SigningKey.generate()
    return bytes(sk) + bytes(sk.verify_key), bytes(sk.verify_key)


def did_from_public_key(public_key: bytes) -> str:
    """Create a did:key:z<base58btc> DID from raw Ed25519 public key bytes.

    Format per W3C did:key spec:
      1. Prepend multicodec prefix 0xed01 to the 32-byte public key
      2. Base58btc-encode the result
      3. Prepend 'z' (base58btc multibase prefix)
      4. Format as did:key:z<encoded>
    """
    prefixed = _ED25519_MULTICODEC_PREFIX + public_key
    return f"did:key:z{_base58btc_encode(prefixed)}"


def parse_did(did: str) -> bytes:
    """Extract Ed25519 public key bytes from a did:key: string."""
    if not did.startswith("did:key:z"):
        raise ValueError(f"Invalid did:key DID (expected did:key:z...): {did}")
    encoded = did[9:]  # strip "did:key:z"
    prefixed = _base58btc_decode(encoded)
    if not prefixed.startswith(_ED25519_MULTICODEC_PREFIX):
        raise ValueError(
            f"DID does not contain an Ed25519 key (expected 0xed01 multicodec prefix): {did}"
        )
    return prefixed[2:]  # strip the 2-byte multicodec prefix
