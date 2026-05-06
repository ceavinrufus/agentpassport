# APS — Agent Protocol Stack

A Python SDK for building multi-agent systems with auth-chain delegation, typed tasks, and observability.

## Install

```bash
pip install aps-sdk              # core
pip install aps-sdk[server]      # + agent server mode
pip install aps-sdk[otel]        # + OpenTelemetry
```

## Quick Start

```python
from aps_sdk import Agent, TaskEnvelope

agent = Agent("my-agent")

@agent.capability("greet")
async def handle_greet(task: TaskEnvelope) -> dict:
    return {"message": f"Hello from {task.input['name']}"}

# Serve as HTTP agent
agent.serve(host="0.0.0.0", port=8000)
```

## Core Concepts

### Agents & Capabilities

An `Agent` is the unit of identity and execution. Each agent has a DID (decentralized identifier) derived from its Ed25519 keypair. Register handlers for named capabilities using the `@agent.capability("name")` decorator — each handler receives a `TaskEnvelope` and returns a dict.

### Auth-Chain Delegation

Agents delegate tasks to other agents while carrying a cryptographically signed chain of authority. Call `await agent.delegate(task, target_did, endpoint, scope=["read"])` to forward a task; the receiving agent can call `verify_auth_chain()` to confirm the full delegation chain is valid.

### Budget & Retry Policies

`BudgetTracker` enforces token/cost ceilings on a task tree; raising `BudgetExceededError` when limits are hit. `RetryExecutor` wraps any coroutine with configurable backoff and attempt limits, controlled by a `FailurePolicy` attached to the `TaskEnvelope`.

### Observability

Every agent emits `ObservabilityEvent` records through an `EventEmitter`. Attach one or more sinks to control where events land:

| Sink | Description |
|------|-------------|
| `StdoutSink` | Print to stdout (default) |
| `FileSink` | Append to a log file |
| `MemorySink` | Buffer in memory (useful for testing) |
| `OtelSink` | Export via OpenTelemetry (`aps-sdk[otel]`) |

### Registry

`RegistryClient` resolves agent DIDs to HTTP endpoints, enabling dynamic discovery. Agents can publish their `AgentCard` (name, DID, capabilities, endpoint) to a running `aps-registry` instance and look up other agents by capability or DID.

## Demo

A 3-agent incident-investigation demo is included — an orchestrator delegates to a Datadog metrics agent and a Lark alerting agent, with mock fallbacks so it works without credentials.

See [`demo/README.md`](demo/README.md) for details.

```bash
uv run python -m demo.run_demo
```

## Packages

| Package | Description |
|---------|-------------|
| `aps-sdk` | Core agent SDK |
| `aps-registry` | Agent discovery registry |
| `aps-adapters` | MCP and other adapters |
| `aps-cli` | CLI tools |

## Development

```bash
uv sync
uv run pytest
```

## License

MIT
