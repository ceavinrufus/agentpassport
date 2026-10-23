"""Trust middleware for pre-execution scope verification.

TrustMiddleware is wired automatically inside Agent.handle(). Users
declare required scope on each capability via the requires= parameter
on the @agent.capability() decorator. The middleware verifies that the
incoming task's auth chain is a valid delegation to this agent and that
it grants every required scope string before the handler runs.

Chain rules match verify_auth_chain():
  - every hop is a signed, unexpired delegation from a known issuer
  - each hop's issuer equals the previous hop's subject
  - scope can only narrow across hops (a previous "*" allows any
    downstream scope)
  - jti and max_delegations are enforced
  - the final token's sub is this agent's DID

The scopes granted to this agent are the final hop's scope list.
"*" there covers any required scope. Otherwise matching is exact:
"read:db:customers" covers only "read:db:customers".

If auth_chain is empty and the capability declares requires, the check
fails. No authorization was granted. A capability with no required
scope is not checked.

Cross-deployment trust is out of scope for this refactor.
# TODO(cross-deployment): placeholder for explicit cross-deployment
# trust establishment between two parties' root signing keys.
"""

from __future__ import annotations

import json

from agentpassport.identity.signing import _decode_jwt_claims, verify_auth_chain


class ScopeError(Exception):
    """Raised when an agent's auth chain does not cover the declared required scope."""


def _final_granted_scopes(auth_chain: list[str]) -> set[str]:
    """Return the scope strings on the final hop of a chain.

    Callers must already have accepted the chain with verify_auth_chain().
    Narrowing is enforced there, so this set is what the receiving agent
    was actually granted.
    """
    try:
        claims = _decode_jwt_claims(auth_chain[-1])
    except (ValueError, json.JSONDecodeError):
        return set()

    scope = claims.get("scope", [])
    if not isinstance(scope, list):
        return set()
    return {item for item in scope if isinstance(item, str)}


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
        """Raise ScopeError if *capability_name* is not authorized.

        No-op when the capability declares no required scope. An empty
        chain, a chain verify_auth_chain() rejects, or a final grant that
        misses a required scope all raise ScopeError. The handler must
        not run in those cases.
        """
        required = self._capability_scopes.get(capability_name)
        if not required:
            return  # capability has no scope requirements — always allowed

        if not task_auth_chain:
            raise ScopeError(
                f"Capability '{capability_name}' requires scope {required!r} "
                f"but the task carries no auth chain."
            )

        if not verify_auth_chain(
            auth_chain=task_auth_chain,
            expected_subject=self._agent_did,
            known_public_keys=self._known_public_keys,
        ):
            raise ScopeError(
                f"Capability '{capability_name}' requires scope {required!r} "
                f"but the auth chain is not a valid delegation to this agent."
            )

        granted = _final_granted_scopes(task_auth_chain)

        # "*" in the final grant covers everything
        if "*" in granted:
            return

        missing = [s for s in required if s not in granted]
        if missing:
            raise ScopeError(
                f"Capability '{capability_name}' requires scope {missing!r} "
                f"not granted by the auth chain. Granted: {sorted(granted)!r}"
            )
