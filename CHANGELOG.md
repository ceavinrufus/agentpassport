# Changelog

All notable changes to agentpassport are documented here.

Format: [Semantic Versioning](https://semver.org). Dates in UTC.

Headings follow git tags: `v0.3.4` is `## [0.3.4]`. A tag is not always the version of every package.

---

## [0.3.4] — 2026-05-29

Python packages and `@agentpassport/core` are aligned on 0.3.4.

### Fixed

**Auth chain**
- `verify_auth_chain` and `verifyAuthChain` reject a hop unless its `iss` is the previous hop's `sub`. Unrelated tokens no longer verify as one chain in those two functions. Python `TrustMiddleware` does not apply this continuity check.
- Scope can only narrow in `verify_auth_chain` and `verifyAuthChain`: a hop that grants a scope the previous hop did not grant is rejected. Python `TrustMiddleware` intersects grants across hops instead of unioning them. TypeScript `TrustMiddleware` did not change in this release.
- `max_delegations` is enforced in `verify_auth_chain` and `verifyAuthChain`. `-1` (the new default) means unlimited, `0` means the recipient cannot delegate further, and `N > 0` means at most N further hops. The most restrictive limit in the chain wins. Previously `0` was stored but treated as unlimited, including on tokens that had already been issued.
- TypeScript `verifyAuthChain` previously checked signatures only. It now applies the same continuity, scope-narrowing, and depth checks as Python `verify_auth_chain`.

**Registry, revocation, and domain binding**
- `DELETE /v1/agents/{did}` requires a signed `X-Delete-Proof` JWT from that agent DID (`sub` is the DID, `action` is `delete`, and `exp` is still in the future).
- Domain-binding verification refuses loopback, private, link-local, and metadata hosts before it fetches `/.well-known/agent-passport.json`.
- SQLite registry writes and SQLite revocation updates take a lock so concurrent writers cannot interleave.
- `iat` checks allow 30 seconds of clock skew.

---

## [0.3.3] — 2026-05-19

### Changed

- `@agentpassport/core` set to 0.3.2 (git tag `v0.3.3`). No API changes. The Python packages stayed on 0.3.0 until 0.3.4.

---

## [0.3.2] — 2026-05-19

Git tag `v0.3.2` shipped documentation and npm packaging. `@agentpassport/core` was 0.3.1 at this tag. The Python packages stayed on 0.3.0 until 0.3.4.

### Added

- Documentation site (MkDocs Material) at [docs.agentpassport.fyi](https://docs.agentpassport.fyi), including the CLI reference and guides for observability, budget tracking, and ownership binding
- LangGraph integration tutorial (`examples/langgraph`)
- Project logo
- npm provenance on publish, plus `files` and `engines` for `@agentpassport/core`

### Changed

- Canonical project domain is [agentpassport.fyi](https://agentpassport.fyi)

### Fixed

- CI requires 80% coverage on the Python SDK
- Docs deploy can push the GitHub Pages branch and serves the custom domain

---

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

[0.3.4]: https://github.com/ceavinrufus/agentpassport/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/ceavinrufus/agentpassport/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/ceavinrufus/agentpassport/compare/v0.3.0...v0.3.2
[0.3.0]: https://github.com/ceavinrufus/agentpassport/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ceavinrufus/agentpassport/releases/tag/v0.2.0
