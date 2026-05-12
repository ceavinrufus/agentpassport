# agentpassport-registry — Trusted Agent Registry

HTTP registry for agentpassport agents. Agents publish signed `AgentCard`s; other agents discover by capability or DID. Signatures are verified before storing — you can prove the agent published its own card.

## Install

```bash
pip install agentpassport-registry
```

## Run

```bash
agentpassport-registry --host 0.0.0.0 --port 8001
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/agents` | Publish a signed AgentCard |
| `GET` | `/v1/agents/{did}` | Resolve agent by DID |
| `GET` | `/v1/agents` | Query by capability |
| `DELETE` | `/v1/agents/{did}` | Remove agent |

## AgentCard

```python
from agentpassport import AgentCard, sign_agent_card

card = AgentCard(
    did=agent.did,
    name="my-agent",
    capabilities=["query_customers"],
    endpoint="https://my-agent.example.com",
)
signed = sign_agent_card(card, agent._private_key)
# POST /v1/agents — registry verifies signature before storing
```

## Development

```bash
uv sync --all-packages
uv run pytest tests/registry/
```
