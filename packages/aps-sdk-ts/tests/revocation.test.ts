import { describe, it, expect } from "vitest";
import { InMemoryRevocationRegistry } from "../src/revocation.js";

describe("InMemoryRevocationRegistry", () => {
  it("isRevoked returns false for unknown jti", () => {
    const reg = new InMemoryRevocationRegistry();
    expect(reg.isRevoked("some-jti")).toBe(false);
  });

  it("isRevoked returns true after revoke()", () => {
    const reg = new InMemoryRevocationRegistry();
    reg.revoke("jti-abc");
    expect(reg.isRevoked("jti-abc")).toBe(true);
  });

  it("revoking one jti does not affect others", () => {
    const reg = new InMemoryRevocationRegistry();
    reg.revoke("jti-1");
    expect(reg.isRevoked("jti-2")).toBe(false);
  });

  it("revoking same jti twice is idempotent", () => {
    const reg = new InMemoryRevocationRegistry();
    reg.revoke("jti-x");
    reg.revoke("jti-x");
    expect(reg.isRevoked("jti-x")).toBe(true);
  });

  it("each instance has independent state", () => {
    const a = new InMemoryRevocationRegistry();
    const b = new InMemoryRevocationRegistry();
    a.revoke("shared-jti");
    expect(b.isRevoked("shared-jti")).toBe(false);
  });
});
