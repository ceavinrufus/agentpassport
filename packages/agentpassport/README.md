# agentpassport — Python SDK

The core Python SDK for agentpassport. Provides cryptographic identity, signed delegation, scope enforcement, and revocation.

## Install

```bash
pip install agentpassport
pip install agentpassport[otel]  # + OpenTelemetry sink
```

## Quickstart

```python
from agentpassport import Agent, sign_delegation, verify_auth_chain

# Create an agent
agent = Agent("my-agent")
print(agent.did)  # did:key:z6Mk...

# Sign a delegation
token = sign_delegation(
    issuer_private_key=root_priv,
    issuer_did=root_did,
    subject_did=agent.did,
    scope=["read:db:customers"],
    ttl_seconds=3600,
)

# Declare required scope on capability
@agent.capability("query_customers", requires=["read:db:customers"])
async def handle(task):
    return {"customers": [...]}

# Revocation
from agentpassport import SqliteRevocationRegistry
registry = SqliteRevocationRegistry("revocations.db")
registry.revoke(jti)
```

## Primitives

- **Identity** — Ed25519 keypair → `did:key:z<base58btc>` DID
- **Auth chain** — list of signed EdDSA JWTs, each hop narrows scope
- **TrustMiddleware** — auto-wired scope verification before capability execution
- **RevocationRegistry** — pluggable ABC; ships `InMemoryRevocationRegistry` + `SqliteRevocationRegistry`
- **AgentCard** — signed capability declaration, verified by registry on publish
- **Observability** — `EventEmitter` with `StdoutSink`, `FileSink`, `MemorySink`, `OtelSink`

## Development

```bash
uv sync --all-packages
uv run pytest
```
