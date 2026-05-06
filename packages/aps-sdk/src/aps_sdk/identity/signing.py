from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

from aps_sdk.types.identity import AuthEntry


def sign_delegation(
    issuer_private_key: bytes,
    issuer_did: str,
    subject_did: str,
    scope: list[str],
    ttl_seconds: int = 3600,
) -> AuthEntry:
    """Create a signed delegation entry."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)

    payload = _canonical_payload(
        issuer_did, subject_did, scope, now.isoformat(), expires.isoformat()
    )

    sk = SigningKey(issuer_private_key[:32])  # First 32 bytes = seed
    signed = sk.sign(payload)
    sig_hex = signed.signature.hex()

    return AuthEntry(
        issuer=issuer_did,
        subject=subject_did,
        scope=scope,
        issued_at=now.isoformat(),
        expires_at=expires.isoformat(),
        sig=sig_hex,
    )


def verify_auth_chain(
    auth_chain: list[AuthEntry],
    expected_subject: str,
    known_public_keys: dict[str, bytes],
) -> bool:
    """Verify the entire auth chain. Returns True if valid."""
    if not auth_chain:
        return False

    for entry in auth_chain:
        pub_key_bytes = known_public_keys.get(entry.issuer)
        if pub_key_bytes is None:
            return False

        payload = _canonical_payload(
            entry.issuer,
            entry.subject,
            entry.scope,
            entry.issued_at,
            entry.expires_at,
        )
        sig_bytes = bytes.fromhex(entry.sig)

        try:
            vk = VerifyKey(pub_key_bytes)
            vk.verify(payload, sig_bytes)
        except (BadSignatureError, Exception):
            return False

    if auth_chain[-1].subject != expected_subject:
        return False

    return True


def _canonical_payload(
    issuer: str,
    subject: str,
    scope: list[str],
    issued_at: str,
    expires_at: str,
) -> bytes:
    """Deterministic bytes for signing."""
    scope_str = ",".join(sorted(scope))
    return f"{issuer}|{subject}|{scope_str}|{issued_at}|{expires_at}".encode("utf-8")
