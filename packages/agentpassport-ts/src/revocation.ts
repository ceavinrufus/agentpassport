// revocation.ts
// RevocationRegistry interface + InMemoryRevocationRegistry

export interface RevocationRegistry {
  revoke(jti: string): void;
  isRevoked(jti: string): boolean;
}

export class InMemoryRevocationRegistry implements RevocationRegistry {
  private readonly _revoked = new Set<string>();

  revoke(jti: string): void {
    this._revoked.add(jti);
  }

  isRevoked(jti: string): boolean {
    return this._revoked.has(jti);
  }
}
