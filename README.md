# APS — Agent Protocol Stack

A trust and authorization layer for multi-agent systems.

**The single question APS answers:**
> "Did this agent have the right to do that — and can you prove it?"

Every other framework trusts that agents are who they say they are and act within scope. APS proves it — cryptographically, at every delegation hop.

## Install

```bash
pip install agentps          # core SDK
pip install agentps[otel]    # + OpenTelemetry sink
```

## Core Concepts

### Identity — `did:key:`

Every agent has an Ed25519 keypair. Its public key is encoded as a W3C-standard `did:key:z<base58btc>` DID — no registry required, verifiable by anyone with the public key.

```python
from aps_sdk import Agent
agent = Agent("my-agent")
print(agent.did)  # did:key:z6Mk...
```

### Auth-Chain Delegation

Trust flows downward through a chain of signed JWT tokens. Each hop narrows or equals the parent scope — an agent can never grant more than it has.

```python
# Deployer signs the initial grant
token = sign_delegation(
    issuer_private_key=root_priv,
    issuer_did=root_did,
    subject_did=agent.did,
    scope=["read:db:customers", "write:api:stripe"],
    ttl_seconds=3600,
)

# Agent verifies before executing
verify_auth_chain(
    auth_chain=[token],
    expected_subject=agent.did,
    known_public_keys={root_did: root_pub},
)
```

Each JWT carries: `iss`, `sub`, `iat`, `exp`, `jti` (required, for revocation), `scope`, `max_delegations`.

### Pre-execution Scope Declaration

Capabilities declare the scope they require. APS verifies the auth chain covers it before the handler runs — fail fast, no partial state.

```python
@agent.capability("query_customers", requires=["read:db:customers"])
async def handle(task: TaskEnvelope) -> dict:
    ...  # only reached if auth chain grants read:db:customers
```

Raises `ScopeError` before the handler is called if the chain is absent or insufficient.

### Signed AgentCard

Capability claims in the agent registry are signed with the agent's private key. The registry verifies the signature before storing — you can prove the agent published its own card.

```python
from aps_sdk import sign_agent_card, verify_agent_card

card = AgentCard(did=agent.did, name="my-agent", capabilities=["query_customers"], endpoint="...")
signed = sign_agent_card(card, agent._private_key)
# Registry verifies on POST /v1/agents
```

### Soft Revocation

Delegations can be revoked by jti without hard-stopping in-flight work. The agent completes its current atomic action and stops before starting the next.

```python
from aps_sdk import InMemoryRevocationRegistry

registry = InMemoryRevocationRegistry()
registry.revoke(jti)  # extracted from the JWT claims

verify_auth_chain(..., revocation_registry=registry)
```

Ship with `InMemoryRevocationRegistry` (in-process) or `SqliteRevocationRegistry` (persistent). Redis/Postgres backends can be added by implementing the `RevocationRegistry` ABC.

### Scope Format

Scopes are `action:resource` pairs — both parts together make authorization provable:

```
["read:db:customers", "write:api:stripe", "send:email:notifications"]
```

Not action-only (`["read"]`) — too loose. Not resource-only (`["db:customers"]`) — incomplete.

### Trust Model

- Trust is **deployment-scoped** — each deployment has its own root signing key
- Trust flows **downward only** — agents can only grant scope they themselves hold
- Each delegation narrows or equals the parent scope, never expands it
- Max delegation depth enforced via `max_delegations` in the JWT claims

### Observability

Every agent emits `ObservabilityEvent` records through an `EventEmitter`. Attach sinks to control where events land:

| Sink | Description |
|------|-------------|
| `StdoutSink` | Print to stdout (default) |
| `FileSink` | Append to a log file |
| `MemorySink` | Buffer in memory (useful for testing) |
| `OtelSink` | Export via OpenTelemetry (`agentps[otel]`) |

### Registry

`RegistryClient` resolves agent DIDs to HTTP endpoints. Agents publish a signed `AgentCard` to `agentps-registry`; other agents discover by capability. The registry verifies card signatures before storing.

## CLI

```bash
# Generate a keypair and DID
aps identity keygen --alias myagent

# View a trace with auth chain verification
aps trace show --id trace_abc --file traces.jsonl
```

The `trace show` command renders each task's auth chain: issuer → subject, scope, expiry, and whether the signature verifies against the DID's embedded public key.

## Packages

| Package | PyPI name | Description |
|---------|-----------|-------------|
| `aps-sdk` | `agentps` | Trust and authorization layer core |
| `aps-registry` | `agentps-registry` | Trusted agent registry with signature verification |
| `aps-adapters` | `agentps-adapters` | MCP and REST adapters |
| `aps-cli` | `agentps-cli` | CLI — keygen, trace viewer |

## What APS is not

- Not a general agent framework — that's LangChain/CrewAI's job
- Not an observability tool — that's OTel's job
- Not an action receipt system — that's Agent Receipts' job

Every feature must answer: *does this help prove whether an agent had the right to do something?*

## Demo

A 3-agent incident-investigation demo is included — an orchestrator delegates to a Datadog metrics agent and a Lark alerting agent, with mock fallbacks.

```bash
uv run python -m demo.run_demo
```

See [`demo/README.md`](demo/README.md) for details.

## Development

```bash
uv sync
uv run pytest
```

## License

MIT
