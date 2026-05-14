"""Trust middleware for pre-execution scope verification.

TrustMiddleware is wired automatically inside Agent.handle(). Users
declare required scope on each capability via the requires= parameter
on the @agent.capability() decorator. The middleware verifies that the
incoming task's auth chain grants every required scope string to this
agent before the handler runs.

Scope matching rules:
  - Exact string match: "read:db:customers" covers "read:db:customers"
  - Wildcard: "*" in the chain scope covers any required scope string
  - No partial glob patterns — exact match or wildcard only

If auth_chain is empty and the capability declares requires, the check
fails. No authorization was granted.

Cross-deployment trust is out of scope for this refactor.
# TODO(cross-deployment): placeholder for explicit cross-deployment
# trust establishment between two parties' root signing keys.
"""

from __future__ import annotations

from datetime import UTC

from nacl.exceptions import BadSignatureError

from agentpassport.identity.signing import _decode_jwt_claims, _verify_jwt_signature


class ScopeError(Exception):
    """Raised when an agent's auth chain does not cover the declared required scope."""


def _chain_granted_scopes(
    auth_chain: list[str],
    agent_did: str,
    known_public_keys: dict[str, bytes],
) -> set[str]:
    """Return the union of scopes granted across all valid tokens in *auth_chain*
    whose subject is *agent_did*.

    Only tokens that pass signature verification and target this agent are
    included. Expired tokens are still skipped — this re-uses the same
    per-token logic as verify_auth_chain but returns scopes rather than bool.
    """
    from datetime import datetime

    granted: set[str] = set()
    now_ts = datetime.now(UTC).timestamp()

    for token in auth_chain:
        try:
            unverified = _decode_jwt_claims(token)
        except Exception:
            continue

        if unverified.get("sub") != agent_did:
            continue

        issuer = unverified.get("iss")
        pub_key_bytes = known_public_keys.get(issuer) if issuer else None
        if pub_key_bytes is None:
            continue

        try:
            claims = _verify_jwt_signature(token, pub_key_bytes)
        except (BadSignatureError, ValueError):
            continue

        try:
            if float(claims["iat"]) > now_ts or now_ts > float(claims["exp"]):
                continue
        except (KeyError, TypeError, ValueError):
            continue

        scope = claims.get("scope", [])
        if isinstance(scope, list):
            granted.update(scope)

    return granted


class TrustMiddleware:
    """Verifies pre-execution scope declarations against the task's auth chain.

    Instantiated once per Agent and called inside Agent.handle() before
    dispatching to the capability handler.
    """

    def __init__(
        self,
        agent_did: str,
        known_public_keys: dict[str, bytes],
        capability_scopes: dict[str, list[str]],
    ) -> None:
        self._agent_did = agent_did
        self._known_public_keys = known_public_keys
        self._capability_scopes = capability_scopes

    def check(self, task_auth_chain: list[str], capability_name: str) -> None:
        """Raise ScopeError if the task's auth chain does not cover the
        required scope declared for *capability_name*.

        If the capability declares no required scope, this is a no-op.
        If the capability declares required scope and the chain is empty,
        ScopeError is raised — no authorization was granted.
        """
        required = self._capability_scopes.get(capability_name)
        if not required:
            return  # capability has no scope requirements — always allowed

        if not task_auth_chain:
            raise ScopeError(
                f"Capability '{capability_name}' requires scope {required!r} "
                f"but the task carries no auth chain."
            )

        granted = _chain_granted_scopes(
            task_auth_chain, self._agent_did, self._known_public_keys
        )

        # "*" in granted covers everything
        if "*" in granted:
            return

        missing = [s for s in required if s not in granted]
        if missing:
            raise ScopeError(
                f"Capability '{capability_name}' requires scope {missing!r} "
                f"not granted by the auth chain. Granted: {sorted(granted)!r}"
            )
