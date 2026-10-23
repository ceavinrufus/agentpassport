# agentpassport-adapters — MCP, REST, CLI, and A2A

Adapters that connect agentpassport agents to external tools and protocols.

## Install

```bash
pip install agentpassport-adapters
```

## Adapters

| Class | What it wraps |
|-------|----------------|
| `McpAdapter` | An MCP server over stdio (`tools/call`) |
| `RestAdapter` | An HTTP endpoint |
| `CliAdapter` | A local command, with `{params.key}` interpolation |
| `A2AServerAdapter` | An agentpassport agent exposed as an A2A server |
| `A2AClientAdapter` | A remote A2A agent, as an agentpassport adapter |

```python
from agentpassport_adapters import McpAdapter, RestAdapter

mcp = McpAdapter(["npx", "-y", "some-mcp-server"])
rest = RestAdapter("https://api.example.com", path="/v1/task")
```

A2A support uses `a2a-sdk` when it is installed, and falls back to the same JSON-RPC wire format when it is not.

## Development

```bash
uv sync --all-packages
uv run pytest tests/adapters/
```
