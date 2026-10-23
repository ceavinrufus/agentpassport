// trust.ts
// TrustMiddleware and ScopeError — scope enforcement before capability dispatch.
// Chain acceptance matches verifyAuthChain: final subject, hop continuity,
// and scope narrowing. The grant is the final hop's scope.

import { decodeJwtClaims, verifyAuthChain } from "./jwt.js";
import type { RevocationRegistry } from "./revocation.js";

export class ScopeError extends Error {
  constructor(
    public readonly capability: string,
    public readonly required: string[],
    public readonly granted: string[],
    detail?: string
  ) {
    const missing = required.filter((s) => !granted.includes(s) && !granted.includes("*"));
    const base =
      `Scope denied for capability "${capability}": ` +
      `requires [${required.join(", ")}], missing [${missing.join(", ")}]`;
    super(detail ? `${base}. ${detail}` : base);
    this.name = "ScopeError";
  }
}

export class TrustMiddleware {
  constructor(
    private readonly agentDid: string,
    private readonly knownPublicKeys: Map<string, Uint8Array>,
    private readonly capabilityScopes: Map<string, string[]>,
    private readonly revocationRegistry?: RevocationRegistry
  ) {}

  /**
   * Check that the auth chain grants the required scope for a capability.
   *
   * - No requires declared → always passes (backward compat)
   * - Empty auth chain + requires declared → ScopeError
   * - Otherwise the whole chain must pass verifyAuthChain for this agent
   *   (subject, continuity, narrowing, signature, expiry, jti,
   *   max_delegations, and revocation when a registry is configured)
   * - Granted scopes are the final hop's scope. "*" covers any requirement;
   *   other scopes match exactly.
   */
  check(authChain: string[], capabilityName: string): void {
    const required = this.capabilityScopes.get(capabilityName);
    if (!required || required.length === 0) return; // no scope required

    if (authChain.length === 0) {
      throw new ScopeError(
        capabilityName,
        required,
        [],
        "The task carries no auth chain."
      );
    }

    const valid = verifyAuthChain({
      chain: authChain,
      expectedSubject: this.agentDid,
      knownPublicKeys: this.knownPublicKeys,
      revocationRegistry: this.revocationRegistry,
    });
    if (!valid) {
      throw new ScopeError(
        capabilityName,
        required,
        [],
        "Auth chain is not a valid delegation to this agent."
      );
    }

    const granted = finalGrantedScopes(authChain);
    if (granted.includes("*")) return;

    const missing = required.filter((s) => !granted.includes(s));
    if (missing.length > 0) {
      throw new ScopeError(capabilityName, required, granted);
    }
  }
}

/** Scope strings on the final hop. The chain must already have verified. */
function finalGrantedScopes(authChain: string[]): string[] {
  try {
    const claims = decodeJwtClaims(authChain[authChain.length - 1]);
    const scope = claims["scope"];
    if (!Array.isArray(scope)) return [];
    return scope.filter((s): s is string => typeof s === "string");
  } catch {
    return [];
  }
}
