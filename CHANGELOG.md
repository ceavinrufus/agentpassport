# Changelog

All notable changes to agentpassport are documented here.

Format: [Semantic Versioning](https://semver.org). Dates in UTC.

---

## [Unreleased]

### Fixed

- **Security:** `Agent.handle()` / `TrustMiddleware.check()` in the Python and TypeScript SDKs now accept a capability's `requires` only when the task's auth chain passes the same rules as `verify_auth_chain()` / `verifyAuthChain()`. A token a trusted issuer gave to agent A is no longer accepted by agent B. A chain with an issuer/subject gap, or a hop that widens scope, is rejected even when the required scope string still appears on the final hop.
- **Security:** `verify_auth_chain()` / `verifyAuthChain()` reject a hop that includes `"*"` when the previous hop did not grant `"*"`. That string used to be skipped in the subset check and then stored as the grant, so the next hop could delegate any scope. A hop that received `"*"` may still pass `"*"` on, and a previous `"*"` still allows any concrete scope downstream. `Agent.handle()` follows this rule.

### Changed

`Agent.handle()` on a capability that declares `requires` is stricter. Capabilities with no `requires` are unchanged.

- The chain is verified as a whole. One bad hop fails the call. Python previously skipped tokens that failed a signature or expiry check and intersected the scopes of whatever remained, without checking `sub`, hop continuity, `jti`, or `max_delegations`. TypeScript previously verified each token on its own and kept only those whose `sub` was this agent, so continuity and narrowing were not enforced.
- The scopes granted to the receiving agent are the **final hop's** `scope`, after that verification. `"*"` on that hop still covers every required scope. Earlier hops constrain it: scope may only narrow, and a previous `"*"` still allows any downstream scope.
- Python `handle()` now applies the same 30-second `iat` leeway as `verify_auth_chain()`. It still does not consult a revocation registry; pass `revocation_registry` to `verify_auth_chain()` when you need that check.
- TypeScript `handle()` still checks the revocation registry when one was passed to `Agent`, and now does so for every hop, not only tokens addressed to this agent.

## [0.3.0] — 2026-05-14

### Added

**Ownership Binding**
- `bind_domain(private_key, did, domain)` — create a signed domain ownership attestation
- `bind_wallet(private_key, did, chain, address)` — create a signed wallet ownership attestation (chain-agnostic: Ethereum, Solana, Bitcoin, and more)
- `revoke_wallet(private_key, did, chain, address)` — create a signed wallet revocation attestation
- `verify_domain_binding(did, domain)` — verify domain binding via `/.well-known/agent-passport.json`
- `verify_wallet_binding(did, chain, address, domain)` — verify wallet binding with revocation check
- `verify_binding_attestation(binding)` — offline signature + expiry verification
- `verify_revocation_attestation(revocation)` — offline revocation signature verification
- `validate_address(chain, address)` — per-chain address format validation (EVM, Solana, Bitcoin)
- `BindingDocument` — array-based document format supporting multiple bindings + revocations
- `Binding` and `Revocation` dataclasses with serialization helpers
- Optional `expires_at` field on all bindings

**CLI commands** (`agentpass identity`)
- `bind-domain` — create and write a domain binding to a file
- `bind-wallet` — create and write a wallet binding to a file
- `revoke-wallet` — create and write a wallet revocation
- `remove-binding` — remove a specific binding by type + claim (fix typos)
- `list-bindings` — inspect a binding document with REVOKED/EXPIRED status
- `verify-domain` — verify a domain binding from the CLI
- `verify-wallet` — verify a wallet binding from the CLI
- All binding CLI commands include confirmation prompts, atomic writes, duplicate detection, and clean error messages

**Demo**
- `demo/binding_demo.py` — interactive demo covering the full ownership binding flow

**Docs**
- `docs/guides/ownership-binding.md` — comprehensive ownership binding guide
- `AGENTS.md` — guidance for AI coding agents working in this repo
- `llms.txt` — machine-readable project overview for LLM consumers

**OSS**
- `LICENSE` — switched from MIT to Apache 2.0
- `CONTRIBUTING.md` — contribution guidelines
- `SECURITY.md` — security policy with threat model, scope, and responsible disclosure

### Fixed
- CI: `uv sync --all-packages` to install all workspace members (fixes `ModuleNotFoundError` for registry/adapters in tests)
- CI: TypeScript jobs pointed to correct `package-lock.json` location (`packages/agentpassport-ts/`)
- Cross-SDK fixture TTL bumped to 100 years — committed fixtures no longer expire
- Ruff lint errors across `packages/` (E402, E501, F401, I001, SIM102, UP042)

---

## [0.2.0] — 2026-05-12

### Added
- Python SDK: `agentpassport` core package
- TypeScript SDK: `@agentpassport/core` (wire-compatible with Python)
- Cross-language delegation chain verification (Ed25519 / EdDSA JWTs)
- `Agent` class with `@agent.capability()` decorator and `TrustMiddleware`
- `sign_delegation` / `verify_auth_chain`
- `InMemoryRevocationRegistry` and `SqliteRevocationRegistry`
- `agentpassport-registry` — FastAPI-based trusted agent registry
- `agentpassport-adapters` — MCP, REST, CLI, and A2A adapters
- `agentpassport-cli` — CLI with `keygen`, `list`, and `trace show`
- OpenTelemetry sink (`agentpassport[otel]`)
- Cross-SDK test suite with fixture-based wire compatibility tests
- `demo/run_demo.py` — interactive cross-SDK trust chain demo

---

[0.3.0]: https://github.com/ceavinrufus/agentpassport/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ceavinrufus/agentpassport/releases/tag/v0.2.0
