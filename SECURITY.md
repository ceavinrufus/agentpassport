# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in agentpassport, please report it responsibly.

**Do not open a public GitHub issue.** Use GitHub's private [Security Advisories](https://github.com/ceavinrufus/agentpassport/security/advisories/new) instead.

**Please include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

**Please do NOT:**
- Open a public GitHub issue for security vulnerabilities
- Exploit the vulnerability beyond what is needed to demonstrate it
- Share the vulnerability publicly before we've had time to address it

**Response time:** We aim to acknowledge within 48 hours and provide a fix timeline within 7 days.

## Scope

This policy covers:
- `agentpassport` — Python trust and authorization SDK
- `@agentpassport/core` — TypeScript SDK
- `agentpassport-registry` — Trusted agent registry
- `agentpassport-adapters` — MCP, REST, and A2A adapters
- `agentpassport-cli` — CLI tooling

## Threat Model

agentpassport operates under these assumptions:

**Trust boundaries:**
- The SDK is a library. It provides cryptographic delegation primitives but cannot enforce behavior unless deployed as the execution boundary.
- `verify_auth_chain()` and the `TrustMiddleware` are enforcement boundaries. When all capability invocations route through them, the protocol enforces scope. Without them, the SDK is advisory only.
- The A2A and MCP adapters enforce within their own sessions but cannot prevent an agent from bypassing the adapter entirely.

**Key management:**
- Ed25519 private keys are generated in-process and are the caller's responsibility to store securely. agentpassport does not persist keys by default.
- Do not commit private keys to version control.
- The `agentpassport-cli` keystore stores keys on disk. Treat keystore files like SSH private keys — restrict file permissions and exclude from version control.

**Delegation chain integrity:**
- JWT delegation tokens are signed with Ed25519. Verification requires the issuer's public key to be in `known_public_keys`. Tokens with unknown issuers are rejected.
- Scope can only narrow at each delegation hop — a delegatee can never grant more than it received. This is enforced by `verify_auth_chain()`.
- Revocation is soft-stop by JTI: in-flight actions complete; the next action is blocked. For hard stops, callers must implement their own preemption.

**Revocation registry:**
- `InMemoryRevocationRegistry` is process-local and non-persistent. State is lost on restart.
- `SqliteRevocationRegistry` persists revocations to disk. Protect the database file with appropriate file permissions.
- agentpassport does not provide a networked revocation distribution mechanism. Propagating revocations across distributed agents is the caller's responsibility.

**Cross-language wire compatibility:**
- Python and TypeScript SDKs share the same JWT wire format. A token signed by one SDK can be verified by the other. Both use Ed25519 via `PyNaCl` (Python) and `@noble/ed25519` (TypeScript).
- Cross-SDK trust depends on both implementations correctly implementing the same signing and verification logic. Any divergence is a security-relevant bug — please report it.

## Supported Versions

| Package | Supported |
|---------|-----------|
| `agentpassport` >= 0.2.0 | ✅ |
| `@agentpassport/core` >= 0.2.0 | ✅ |
| Older versions | ❌ |

## Recognition

We gratefully acknowledge security researchers who report vulnerabilities responsibly. With your permission, we will credit you in the changelog.
