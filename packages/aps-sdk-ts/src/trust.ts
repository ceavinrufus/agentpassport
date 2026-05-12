// trust.ts
// TrustMiddleware and ScopeError — scope enforcement before capability dispatch

import { verifyAuthChain } from "./jwt.js";
import type { RevocationRegistry } from "./revocation.js";

export class ScopeError extends Error {
  constructor(
    public readonly capability: string,
    public readonly required: string[],
    public readonly granted: string[]
  ) {
    const missing = required.filter((s) => !granted.includes(s) && !granted.includes("*"));
    super(
      `Scope denied for capability "${capability}": ` +
        `requires [${required.join(", ")}], missing [${missing.join(", ")}]`
    );
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
   * - Scope matching: exact string OR "*" wildcard only
   */
  check(authChain: string[], capabilityName: string): void {
    const required = this.capabilityScopes.get(capabilityName);
    if (!required || required.length === 0) return; // no scope required

    // Collect granted scopes from all tokens whose sub == agentDid
    // and whose issuer is trusted
    const granted = new Set<string>();

    for (const token of authChain) {
      try {
        // Quick decode without verification to check sub
        const parts = token.split(".");
        if (parts.length !== 3) continue;
        const claims = JSON.parse(
          new TextDecoder().decode(
            (() => {
              const s = parts[1].replace(/-/g, "+").replace(/_/g, "/");
              const padding = (4 - (s.length % 4)) % 4;
              const binary = atob(s + "=".repeat(padding));
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
              return bytes;
            })()
          )
        );

        if (claims.sub !== this.agentDid) continue;
        if (!this.knownPublicKeys.has(claims.iss)) continue;

        // Verify this token cryptographically
        const valid = verifyAuthChain({
          chain: [token],
          expectedSubject: this.agentDid,
          knownPublicKeys: this.knownPublicKeys,
          revocationRegistry: this.revocationRegistry,
        });

        if (valid && Array.isArray(claims.scope)) {
          for (const s of claims.scope) granted.add(s as string);
        }
      } catch {
        // malformed token — skip
      }
    }

    // Wildcard grants everything
    if (granted.has("*")) return;

    // Check each required scope
    const missing = required.filter((s) => !granted.has(s));
    if (missing.length > 0) {
      throw new ScopeError(capabilityName, required, Array.from(granted));
    }
  }
}
