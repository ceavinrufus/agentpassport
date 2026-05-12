from __future__ import annotations

# AuthEntry has been removed. The auth chain is now list[str] — a list of
# compact EdDSA JWT strings, one per delegation hop.
#
# Each JWT carries the following claims:
#   iss             — issuer DID (did:key:z...)
#   sub             — subject DID (did:key:z...)
#   iat             — issued-at (unix timestamp)
#   exp             — expiry (unix timestamp)
#   jti             — unique token ID (UUID4, required for revocation)
#   scope           — list[str] of action:resource permission strings
#   max_delegations — remaining delegation depth
#
# See identity/signing.py for sign_delegation() and verify_auth_chain().
