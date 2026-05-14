# Changelog

All notable changes to agentpassport are documented here.

Format: [Semantic Versioning](https://semver.org). Dates in UTC.

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

[0.3.0]: https://github.com/ceavinrufus/agentpassport/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ceavinrufus/agentpassport/releases/tag/v0.2.0
