from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from agentpassport.revocation import RevocationRegistry
from agentpassport.types.agent_card import AgentCard


# ---------------------------------------------------------------------------
# Internal JWT helpers (EdDSA / Ed25519, compact serialisation)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


_JWT_HEADER = _b64url_encode(
    json.dumps({"alg": "EdDSA", "crv": "Ed25519"}, separators=(",", ":")).encode()
)


def _encode_jwt(claims: dict, private_key_seed: bytes) -> str:
    """Produce a compact EdDSA JWT from *claims* signed with *private_key_seed*."""
    payload = _b64url_encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    )
    signing_input = f"{_JWT_HEADER}.{payload}".encode()
    sk = SigningKey(private_key_seed)
    sig = _b64url_encode(sk.sign(signing_input).signature)
    return f"{_JWT_HEADER}.{payload}.{sig}"


def _decode_jwt_claims(token: str) -> dict:
    """Decode and return the claims of a JWT without verifying the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(f"Malformed JWT: expected 3 parts, got {len(parts)}")
    return json.loads(_b64url_decode(parts[1]))


def _verify_jwt_signature(token: str, public_key_bytes: bytes) -> dict:
    """Verify the JWT signature and return the decoded claims.

    Raises ValueError on structural problems, BadSignatureError on bad sig.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(f"Malformed JWT: expected 3 parts, got {len(parts)}")

    header_claims = json.loads(_b64url_decode(parts[0]))
    if header_claims.get("alg") != "EdDSA":
        raise ValueError(f"Unsupported JWT algorithm: {header_claims.get('alg')!r}")

    signing_input = f"{parts[0]}.{parts[1]}".encode()
    sig_bytes = _b64url_decode(parts[2])

    vk = VerifyKey(public_key_bytes)
    vk.verify(signing_input, sig_bytes)  # raises BadSignatureError on failure

    return json.loads(_b64url_decode(parts[1]))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sign_delegation(
    issuer_private_key: bytes,
    issuer_did: str,
    subject_did: str,
    scope: list[str],
    ttl_seconds: int = 3600,
    max_delegations: int = 0,
) -> str:
    """Create a signed delegation JWT for one hop in the trust chain.

    Returns a compact JWT string (header.payload.signature).

    Claims:
        iss             — issuer DID (did:key:z...)
        sub             — subject DID (did:key:z...)
        iat             — issued-at unix timestamp
        exp             — expiry unix timestamp
        jti             — unique token ID (UUID4, required for revocation)
        scope           — list of action:resource permission strings
        max_delegations — remaining delegation depth this token permits
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)

    claims = {
        "iss": issuer_did,
        "sub": subject_did,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),
        "scope": scope,
        "max_delegations": max_delegations,
    }

    seed = issuer_private_key[:32]  # first 32 bytes are the Ed25519 seed
    return _encode_jwt(claims, seed)


def verify_auth_chain(
    auth_chain: list[str],
    expected_subject: str,
    known_public_keys: dict[str, bytes],
    revocation_registry: RevocationRegistry | None = None,
) -> bool:
    """Verify a chain of delegation JWTs.

    Each token must:
      - be a structurally valid EdDSA JWT
      - have its issuer DID present in *known_public_keys*
      - carry a valid signature from that issuer
      - not be expired (exp) or used before issuance (iat)
      - carry a non-empty jti claim

    The final token's sub must equal *expected_subject*.

    If *revocation_registry* is provided, each token's jti is checked
    against it and rejected if revoked (placeholder for step 6).

    Returns True only if every check passes for every hop.
    """
    if not auth_chain:
        return False

    now_ts = datetime.now(timezone.utc).timestamp()

    for token in auth_chain:
        # --- resolve issuer public key from unverified claims first ---
        try:
            unverified = _decode_jwt_claims(token)
        except (ValueError, KeyError, json.JSONDecodeError):
            return False

        issuer = unverified.get("iss")
        pub_key_bytes = known_public_keys.get(issuer) if issuer else None
        if pub_key_bytes is None:
            return False

        # --- cryptographic verification ---
        try:
            claims = _verify_jwt_signature(token, pub_key_bytes)
        except (BadSignatureError, ValueError):
            return False

        # --- temporal validity ---
        try:
            iat = float(claims["iat"])
            exp = float(claims["exp"])
        except (KeyError, TypeError, ValueError):
            return False

        if iat > now_ts or now_ts > exp:
            return False

        # --- jti required ---
        if not claims.get("jti"):
            return False

        # --- revocation check ---
        if revocation_registry is not None:
            if revocation_registry.is_revoked(claims["jti"]):
                return False

    # --- final subject check ---
    try:
        last_claims = _decode_jwt_claims(auth_chain[-1])
    except (ValueError, json.JSONDecodeError):
        return False

    return last_claims.get("sub") == expected_subject


# ---------------------------------------------------------------------------
# AgentCard signing
# ---------------------------------------------------------------------------

def sign_agent_card(card: AgentCard, private_key_seed: bytes) -> AgentCard:
    """Return a new AgentCard with the signature field populated.

    Signs over card.canonical_payload() (SHA-256 hash of the deterministic
    JSON of name, did, capabilities, endpoint) with the Ed25519 private key.
    The signature is hex-encoded.
    """
    sk = SigningKey(private_key_seed[:32])
    payload = card.canonical_payload()
    sig_hex = sk.sign(payload).signature.hex()
    return card.model_copy(update={"signature": sig_hex})


def verify_agent_card(card: AgentCard, public_key_bytes: bytes) -> bool:
    """Verify the AgentCard's signature field against its canonical payload.

    Returns False if the card has no signature, or if verification fails.
    """
    if not card.signature:
        return False
    try:
        sig_bytes = bytes.fromhex(card.signature)
        vk = VerifyKey(public_key_bytes)
        vk.verify(card.canonical_payload(), sig_bytes)
        return True
    except (BadSignatureError, ValueError):
        return False
