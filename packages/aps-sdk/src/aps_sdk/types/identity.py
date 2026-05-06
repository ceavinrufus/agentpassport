from __future__ import annotations
from pydantic import BaseModel


class AuthEntry(BaseModel):
    """One hop in the trust delegation chain."""

    issuer: str  # did:aps:<id>
    subject: str  # did:aps:<id>
    scope: list[str]
    issued_at: str  # ISO8601
    expires_at: str  # ISO8601
    sig: str  # hex-encoded Ed25519 signature
