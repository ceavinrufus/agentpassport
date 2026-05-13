# AgentPassport Adapters — API Reference

Complete reference for the `agentpassport-adapters` package. Adapters bridge the `TaskEnvelope` protocol to external services that don't speak AgentPassport natively.

---

## Table of Contents

- [Installation](#installation)
- [Abstract base: `Adapter`](#abstract-base-adapter)
- [Class: `McpAdapter`](#class-mcpadapter)
- [Class: `RestAdapter`](#class-restadapter)
- [Class: `CliAdapter`](#class-cliadapter)
- [Integration patterns](#integration-patterns)

---

## Installation

```bash
pip install agentpassport-adapters
```

Depends on `agentpassport` and `httpx`.

---

## Abstract base: `Adapter`

**Module:** `agentpassport_adapters.base`

```python
from abc import ABC, abstractmethod
from agentpassport.types import TaskEnvelope

class Adapter(ABC):
    @abstractmethod
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]:
        """Execute a task through the adapted service."""
        ...
```

All adapters implement this interface. The `execute()` method receives a `TaskEnvelope` and returns a dict result. Agents typically wrap an adapter inside a capability handler.

---

## Class: `McpAdapter`

**Module:** `agentpassport_adapters.mcp`

```python
class McpAdapter(Adapter):
    def __init__(self, command: list[str]) -> None
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Translates a `TaskEnvelope` into a JSON-RPC 2.0 `tools/call` request sent to an MCP (Model Context Protocol) server over stdio.

### Constructor

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | `list[str]` | Yes | The subprocess command to launch the MCP server. Each element is a separate argument (not a shell string). |

### `McpAdapter.execute()`

```python
async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Sends a `tools/call` request to the MCP server and returns the result.

**Request structure sent to MCP server (NDJSON over stdin):**
```json
{
  "jsonrpc": "2.0",
  "id": "<task.id>",
  "method": "tools/call",
  "params": {
    "name": "<task.intent.type>",
    "arguments": { ...task.intent.params }
  }
}
```

**Returns:** `dict` — the `result` field from the MCP server's JSON-RPC response.

**Raises:**
- `RuntimeError` — if the subprocess exits with a non-zero exit code. Message includes stderr output.
- `RuntimeError` — if the response JSON contains an `"error"` key. Message includes the error content.
- `json.JSONDecodeError` — if the MCP server returns non-JSON output.

**How it works:**
1. Launches the MCP server subprocess (`asyncio.create_subprocess_exec`).
2. Writes the JSON-RPC request as a newline-terminated line to stdin.
3. Calls `communicate()` to send the request and read the full response from stdout.
4. Parses the response and returns `response["result"]`.

**Important:** The subprocess is launched fresh for **each call**. If your MCP server has significant startup time, consider keeping a persistent subprocess or using a connection pool.

**Example 1: Wrap a Node.js MCP server**
```python
from agentpassport import Agent, TaskEnvelope
from agentpassport_adapters import McpAdapter

agent = Agent(name="mcp-bridge")
mcp = McpAdapter(command=["node", "my-mcp-server.js"])

@agent.capability("web_search")
async def web_search(task: TaskEnvelope) -> dict:
    # task.intent.type = "web_search" → MCP tools/call name = "web_search"
    # task.intent.params = {"query": "..."} → MCP arguments = {"query": "..."}
    return await mcp.execute(task)
```

**Example 2: Wrap a Python MCP server**
```python
mcp = McpAdapter(command=["python", "-m", "my_mcp_server"])

@agent.capability("read_file")
async def read_file(task: TaskEnvelope) -> dict:
    return await mcp.execute(task)
```

**Example 3: Error handling**
```python
@agent.capability("risky_tool")
async def risky_tool(task: TaskEnvelope) -> dict:
    try:
        return await mcp.execute(task)
    except RuntimeError as e:
        if "MCP server failed" in str(e):
            return {"error": "mcp_server_error", "detail": str(e)}
        raise
```

---

## Class: `RestAdapter`

**Module:** `agentpassport_adapters.rest`

```python
class RestAdapter(Adapter):
    def __init__(
        self,
        base_url: str,
        method: str = "POST",
        path: str = "/",
        body_template: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None
    def build_request(self, task: TaskEnvelope) -> dict[str, Any]
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Translates a `TaskEnvelope` into an HTTP request to a REST API. Supports `{params.key}` template interpolation in the URL path and request body.

### Constructor

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | `str` | Yes | — | Base URL of the REST API (e.g. `"https://api.example.com"`) |
| `method` | `str` | No | `"POST"` | HTTP method (`"GET"`, `"POST"`, `"PUT"`, `"PATCH"`, `"DELETE"`) |
| `path` | `str` | No | `"/"` | URL path, optionally with `{params.key}` placeholders |
| `body_template` | `dict \| None` | No | `{}` | Request body dict with `{params.key}` placeholders |
| `headers` | `dict \| None` | No | `{}` | Additional HTTP headers (e.g. `{"Authorization": "Bearer ..."}`) |

### Template interpolation

Both `path` and values in `body_template` support `{params.key}` placeholders. These are replaced with the corresponding value from `task.intent.params`. Nested dict values in `body_template` are interpolated recursively. Non-string values are passed through unchanged.

**Example template:**
```python
body_template = {
    "query": "{params.query}",
    "limit": 10,           # int — not interpolated
    "nested": {
        "field": "{params.field}",
    },
}
```

With `task.intent.params = {"query": "hello", "field": "x"}`, the body becomes:
```json
{"query": "hello", "limit": 10, "nested": {"field": "x"}}
```

### `RestAdapter.build_request()`

```python
def build_request(self, task: TaskEnvelope) -> dict[str, Any]
```

Build the HTTP request dict from the task params without executing it. Useful for testing or logging.

**Returns:** `dict` with keys `"method"`, `"url"`, `"body"`.

### `RestAdapter.execute()`

```python
async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Build and execute the HTTP request using `httpx.AsyncClient`.

**Returns:** Parsed JSON response body as a dict.

**Raises:**
- `httpx.HTTPStatusError` — on non-2xx responses.
- `httpx.RequestError` — on network failures.

**Example 1: POST to an external API**
```python
from agentpassport import Agent, TaskEnvelope
from agentpassport_adapters import RestAdapter

agent = Agent(name="openai-bridge")

openai_adapter = RestAdapter(
    base_url="https://api.openai.com",
    method="POST",
    path="/v1/chat/completions",
    body_template={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "{params.prompt}"}],
    },
    headers={"Authorization": "Bearer sk-..."},
)

@agent.capability("chat", requires=["invoke:llm"])
async def chat(task: TaskEnvelope) -> dict:
    response = await openai_adapter.execute(task)
    return {"reply": response["choices"][0]["message"]["content"]}
```

**Example 2: Inspect the request without executing**
```python
from agentpassport import TaskEnvelope, Intent

adapter = RestAdapter(
    base_url="https://api.example.com",
    path="/search",
    body_template={"q": "{params.query}", "limit": 10},
)
task = TaskEnvelope(intent=Intent(type="search", params={"query": "hello"}))
req = adapter.build_request(task)
print(req)
# {'method': 'POST', 'url': 'https://api.example.com/search', 'body': {'q': 'hello', 'limit': 10}}
```

**Example 3: REST GET with path params**
```python
# If path contains params, use a path template:
adapter = RestAdapter(
    base_url="https://api.example.com",
    method="GET",
    path="/users/{params.user_id}/profile",
    body_template={},
)
# For GET, body is still sent as JSON — some APIs ignore GET bodies.
# Alternatively, add params to the query string via a custom headers dict.
```

---

## Class: `CliAdapter`

**Module:** `agentpassport_adapters.cli`

```python
class CliAdapter(Adapter):
    def __init__(self, command_template: str) -> None
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Translates a `TaskEnvelope` into a subprocess invocation. Uses `{params.key}` interpolation in the command template, with shell escaping for safety.

### Constructor

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command_template` | `str` | Yes | Shell command string with `{params.key}` placeholders. Each placeholder is shell-escaped with `shlex.quote()` before substitution. |

**Example template:** `"curl -s {params.url}"` with `params={"url": "https://example.com"}` becomes `curl -s 'https://example.com'`.

### `CliAdapter.execute()`

```python
async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Build and run the command via `asyncio.create_subprocess_shell`.

**Returns:**
- If the command's stdout is valid JSON: the parsed dict.
- If stdout is not valid JSON: `{"output": "<raw stdout>", "exit_code": <int>}`.

**Raises:** Nothing — exit code errors are captured in the return dict. JSON parse errors are caught and the raw output is returned.

**Security note:** All `{params.key}` values are shell-escaped with `shlex.quote()`. However, the command template itself is a shell string. Do not put untrusted input in the template itself.

**Example 1: Wrap a CLI tool that produces JSON**
```python
from agentpassport import Agent, TaskEnvelope
from agentpassport_adapters import CliAdapter

agent = Agent(name="cli-bridge")

jq_adapter = CliAdapter(command_template="cat {params.filepath} | jq .")

@agent.capability("read_json_file")
async def read_json_file(task: TaskEnvelope) -> dict:
    result = await jq_adapter.execute(task)
    return result  # parsed JSON from jq
```

**Example 2: Wrap curl**
```python
curl_adapter = CliAdapter(command_template="curl -s {params.url}")

@agent.capability("fetch_url")
async def fetch_url(task: TaskEnvelope) -> dict:
    result = await curl_adapter.execute(task)
    # If the URL returns JSON, result is already parsed
    # If not, result = {"output": "<raw html>", "exit_code": 0}
    return result
```

**Example 3: Non-JSON tool**
```python
ls_adapter = CliAdapter(command_template="ls -la {params.directory}")

@agent.capability("list_directory")
async def list_directory(task: TaskEnvelope) -> dict:
    result = await ls_adapter.execute(task)
    # result = {"output": "total 48\ndrwxr-xr-x ...", "exit_code": 0}
    files = result.get("output", "").splitlines()
    return {"files": files[1:], "count": len(files) - 1}  # skip "total" line
```

---

## Integration patterns

### Pattern 1: Adapter as a capability backend

The most common pattern. An `Agent` wraps an adapter inside a `@capability` handler. The agent handles auth chain verification and scope enforcement; the adapter handles the external call.

```python
from agentpassport import Agent, TaskEnvelope
from agentpassport_adapters import McpAdapter, RestAdapter

agent = Agent(name="multi-adapter-agent")

# Different capabilities use different adapters
mcp = McpAdapter(command=["node", "tools-server.js"])
openai = RestAdapter(
    base_url="https://api.openai.com",
    path="/v1/chat/completions",
    body_template={"model": "gpt-4o", "messages": [{"role": "user", "content": "{params.prompt}"}]},
    headers={"Authorization": f"Bearer {OPENAI_KEY}"},
)

@agent.capability("use_tool", requires=["invoke:tool"])
async def use_tool(task: TaskEnvelope) -> dict:
    return await mcp.execute(task)

@agent.capability("generate_text", requires=["invoke:llm"])
async def generate_text(task: TaskEnvelope) -> dict:
    return await openai.execute(task)
```

### Pattern 2: Adapter with error translation

```python
import httpx

@agent.capability("search", requires=["invoke:search"])
async def search(task: TaskEnvelope) -> dict:
    try:
        return await rest_adapter.execute(task)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return {"error": "rate_limited", "retry_after": e.response.headers.get("Retry-After")}
        elif e.response.status_code == 401:
            return {"error": "unauthorized"}
        raise
    except httpx.RequestError as e:
        return {"error": "network_error", "detail": str(e)}
```

### Pattern 3: Adapter with result transformation

```python
@agent.capability("summarize", requires=["invoke:llm"])
async def summarize(task: TaskEnvelope) -> dict:
    # Raw OpenAI response
    raw = await openai_adapter.execute(task)

    # Transform into AgentPassport result format
    return {
        "summary": raw["choices"][0]["message"]["content"],
        "usage": {
            "prompt_tokens": raw["usage"]["prompt_tokens"],
            "completion_tokens": raw["usage"]["completion_tokens"],
        },
    }
```

---

## A2A Adapters

agentpassport ships two A2A adapters that bridge the [Agent2Agent (A2A) protocol](https://a2a-protocol.org) with agentpassport's trust model.

**Module:** `agentpassport_adapters.a2a`

```python
from agentpassport_adapters import A2AServerAdapter, A2AClientAdapter, synthesize_a2a_agent_card
```

**Install:**

```bash
pip install agentpassport-adapters starlette httpx
# Optional: pip install a2a-sdk  (for protobuf-backed serialization)
```

---

### `synthesize_a2a_agent_card()`

```python
def synthesize_a2a_agent_card(
    aps_card: AgentCard,
    endpoint: str | None = None,
) -> dict[str, Any]
```

Convert an agentpassport `AgentCard` to an A2A AgentCard dict suitable for serving at `/.well-known/agent-card.json`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `aps_card` | `AgentCard` | Yes | The agentpassport AgentCard to convert. |
| `endpoint` | `str \| None` | No | Override the endpoint URL. Defaults to `aps_card.endpoint`. |

**Returns:** `dict` — A2A AgentCard wire format. Safe to pass to `json.dumps`.

Agentpassport-specific fields are preserved as extension fields:
- `x_agentpassport_did` — the agent's DID
- `x_agentpassport_signature` — the AgentCard signature (if present)

---

### Class: `A2AServerAdapter`

**Pattern B — expose an agentpassport agent as an A2A server.**

```python
class A2AServerAdapter:
    def __init__(
        self,
        agent: Agent,
        agent_card: AgentCard | None = None,
        endpoint: str = "",
        skill_map: dict[str, str] | None = None,
    ) -> None
    def build_app(self) -> Starlette
```

Wraps an agentpassport `Agent` in a Starlette application that speaks the A2A protocol. Any A2A-compatible client (LangGraph, Google ADK, Salesforce Agentforce, etc.) can discover and call your agent.

**Constructor parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent` | `Agent` | Yes | The agentpassport agent to expose. |
| `agent_card` | `AgentCard \| None` | No | Pre-built AgentCard. If omitted, falls back to `agent.card`. |
| `endpoint` | `str` | No | Public HTTP URL for this server. Included in the A2A AgentCard. |
| `skill_map` | `dict[str, str] \| None` | No | Maps A2A skill ids → agentpassport capability names. By default, skill id == capability name. |

**`build_app()` returns** a `Starlette` app with two routes:
- `GET /.well-known/agent-card.json` — A2A discovery endpoint
- `POST /` — JSON-RPC 2.0 handler for `message/send`

**Auth chain:** extracted from `X-AgentPassport-Auth-Chain` header (comma-separated JWTs). Capabilities without `requires=` work for any A2A client with no auth chain.

**Errors:**
- `ScopeError` → JSON-RPC error response (not HTTP 500)
- Unknown skill → JSON-RPC error listing available capabilities
- Multiple capabilities with no `skillId` in request → JSON-RPC error

**Example:**

```python
import uvicorn
from agentpassport import Agent, AgentCard, sign_agent_card, generate_keypair
from agentpassport_adapters import A2AServerAdapter

priv, pub = generate_keypair()
agent = Agent("my-agent", private_key=priv)

@agent.capability("search", requires=["search:web"])
async def search(task):
    return {"results": ["..."]}

@agent.capability("ping")  # open — no auth required
async def ping(task):
    return {"pong": True}

card = AgentCard(did=agent.did, name="my-agent",
                 capabilities=["search", "ping"], endpoint="http://localhost:8000")

server = A2AServerAdapter(agent=agent, agent_card=card, endpoint="http://localhost:8000")
app = server.build_app()

uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### Class: `A2AClientAdapter`

**Pattern A — delegate to an external A2A agent.**

```python
class A2AClientAdapter(Adapter):
    def __init__(
        self,
        agent_card_url: str,
        auth_token: str | None = None,
        timeout: float = 30.0,
    ) -> None
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

Wraps a remote A2A agent as an agentpassport `Adapter`. Fetches the remote AgentCard, translates `TaskEnvelope` → A2A `SendMessageRequest`, polls to completion, and returns the result.

**Constructor parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_card_url` | `str` | Yes | URL of the remote A2A agent's `/.well-known/agent-card.json`. |
| `auth_token` | `str \| None` | No | Bearer token for transport-level auth (A2A OAuth2). |
| `timeout` | `float` | No | Request and polling timeout in seconds. Default `30.0`. |

**`execute(task)` behaviour:**
1. Fetches and caches the remote AgentCard (once per adapter instance).
2. Translates `task.intent.type` → A2A skill selection, `task.intent.params` → `DataPart`.
3. Injects `task.auth_chain` as `X-AgentPassport-Auth-Chain` header if non-empty.
4. Sends `message/send` JSON-RPC request.
5. Polls with exponential backoff (0.5s → 5s) until terminal state.
6. Parses result text as JSON if possible; returns dict.

**Raises:**
- `RuntimeError` — remote task failed, JSON-RPC error, or AgentCard fetch failed.
- `TimeoutError` — task did not complete within `timeout` seconds.

**Example:**

```python
from agentpassport import Agent
from agentpassport_adapters import A2AClientAdapter

agent = Agent("orchestrator")
salesforce_adapter = A2AClientAdapter(
    agent_card_url="https://agents.salesforce.com/.well-known/agent-card.json",
    auth_token="Bearer <oauth-token>",
    timeout=60.0,
)

@agent.capability("crm_lookup")
async def crm_lookup(task):
    return await salesforce_adapter.execute(task)
```
