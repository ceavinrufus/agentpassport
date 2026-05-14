# AGENTS.md — agentpassport

Guidance for AI coding agents (Copilot, Cursor, Claude, etc.) working in this repo.

## What This Project Is

agentpassport is an auth layer for AI agents — cryptographic identity, signed delegation chains, scope enforcement, and revocation. Python + TypeScript, wire-compatible.

## Repo Structure

```
packages/
  agentpassport/          # Python SDK (core)
    identity/
      did.py              # DID generation and parsing
      signing.py          # JWT signing and verification
      binding.py          # Domain and wallet ownership binding
      keystore.py         # File-based key storage
  agentpassport-ts/       # TypeScript SDK
  agentpassport-registry/ # Trusted agent registry (FastAPI)
  agentpassport-adapters/ # MCP, REST, A2A adapters
  agentpassport-cli/      # CLI tooling
tests/
  sdk/                    # Python SDK unit tests
  adapters/               # Adapter unit tests
  registry/               # Registry unit tests
  cli/                    # CLI unit tests
  cross-sdk/              # Python ↔ TypeScript wire compatibility tests
  demo/                   # End-to-end demo tests
demo/                     # Interactive demo scripts
docs/
  guides/                 # Guides (quickstart, cross-sdk, binding, etc.)
  python/                 # Python API reference
  typescript/             # TypeScript API reference
```

## Running Tests

```bash
# Python (all packages)
uv sync --all-packages
uv run pytest

# TypeScript
cd packages/agentpassport-ts
npm ci && npm test

# Lint
uv run ruff check .
```

## Code Conventions

- **Python:** type hints everywhere, PEP 8, ruff enforced. No bare `except`. No mutable default args.
- **TypeScript:** strict mode, named exports, no `any`.
- **Tests:** pytest for Python, vitest for TypeScript. Every new function needs tests. Cover happy path + error cases.
- **Commits:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`). Keep scope focused.

## Key APIs

### Python

```python
from agentpassport import (
    generate_keypair, did_from_public_key,
    sign_delegation, verify_auth_chain,
    bind_domain, bind_wallet, verify_domain_binding, verify_wallet_binding,
    InMemoryRevocationRegistry, SqliteRevocationRegistry,
)
```

### TypeScript

```typescript
import { Agent, generateKeypair, signDelegation, verifyAuthChain } from "@agentpassport/core"
```

## What to Avoid

- Do not modify `tests/cross-sdk/fixtures.json` or `ts_fixtures.json` manually — they are generated
- Do not add runtime dependencies without updating the relevant `pyproject.toml` or `package.json`
- Do not commit private keys or credentials
- Do not bypass `verify_auth_chain()` or `TrustMiddleware` in examples — this defeats the purpose of the library
- Do not change the JWT wire format without updating both Python and TypeScript SDKs and the cross-SDK tests
- Do not change the binding document format (`/.well-known/agent-passport.json`) without updating `binding.py`, the ownership binding guide, and `llms.txt`

## Adding Features

1. Implement in the relevant package under `packages/`
2. Export from the package `__init__.py`
3. Add tests in `tests/`
4. Run `uv run ruff check .` and `uv run pytest` before committing
5. Update `README.md` if the public API changes
