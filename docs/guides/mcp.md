# Guide: MCP Middleware — Enforcing Passport and Scope Before Tool Execution

This guide shows how to check an agentpassport delegation chain before an MCP tool runs. MCP authorization, when a server uses it, already decides which client may reach the server. agentpassport does not replace that. It records what each agent in a delegation chain was allowed to do.

---

## Table of Contents

1. [Where this sits relative to MCP auth](#1-where-this-sits-relative-to-mcp-auth)
2. [What the middleware checks](#2-what-the-middleware-checks)
3. [Architecture overview](#3-architecture-overview)
4. [Pattern A: Agent wraps McpAdapter with scope enforcement](#4-pattern-a-agent-wraps-mcpadapter-with-scope-enforcement)
5. [Pattern B: HTTP proxy — enforce passport before forwarding to MCP server](#5-pattern-b-http-proxy--enforce-passport-before-forwarding-to-mcp-server)
6. [Pattern C: Inline middleware in your MCP server handler](#6-pattern-c-inline-middleware-in-your-mcp-server-handler)
7. [Scope design for MCP tools](#7-scope-design-for-mcp-tools)
8. [Revocation mid-flight](#8-revocation-mid-flight)
9. [Full runnable example](#9-full-runnable-example)
10. [Reference: McpAdapter](#10-reference-mcpadapter)

---

## 1. Where this sits relative to MCP auth

MCP defines authorization for HTTP transports. Support is optional. When a server uses it, the mechanism is [OAuth 2.1](https://modelcontextprotocol.io/specification/latest/basic/authorization): the server is a resource server, and a bearer token decides which client may call it. stdio transports are outside that flow. The spec says they should take credentials from the environment instead.

That answers a different question from delegation:

- An authorized client can hand the tool call to another agent.
- The server still sees one client. It does not see a signed grant from that client to the next agent, or a scope that narrowed at that hop.
- Revoking the downstream grant is not the same operation as revoking the client's OAuth token.

agentpassport sits on top of OAuth and MCP auth. It does not replace them, and it is not an MCP authorization server.

---

## 2. What the middleware checks

The patterns below run after the client is allowed to reach the server, and before the tool:

1. **Scope** — `TrustMiddleware.check` requires the task's auth chain to grant the scope declared for the tool. It verifies JWT signatures against keys you have trusted, and it skips expired tokens and tokens from unknown issuers.
2. **Stop on failure** — `ScopeError` is raised before `McpAdapter.execute`, or before the proxy forwards, so the tool does not run.
3. **Forward on success** — the tool call goes to the MCP server. The auth chain is not forwarded. The server does not have to understand agentpassport.

`TrustMiddleware.check` does not consult a revocation registry. To reject a revoked `jti`, call `verify_auth_chain(..., revocation_registry=...)`. See [section 8](#8-revocation-mid-flight).

In the wrapper and proxy patterns the MCP server process is unchanged. OAuth on an HTTP server, if you use it, still decides which client may connect.

---

## 3. Architecture overview

```
Agent / LLM orchestrator
  │
  │  TaskEnvelope { intent.type="read_file", auth_chain=[JWT1, JWT2] }
  ▼
agentpassport Agent (Python)
  ├── TrustMiddleware.check(auth_chain, "read_file")
  │     ├── each token: signature, expiry, issuer key is trusted
  │     ├── granted scope includes "fs:read", or "*"
  │     └── chain linkage and revocation: use verify_auth_chain
  │
  ├── if check passes ──▶  McpAdapter.execute(task)
  │                           ├── spawn MCP server subprocess
  │                           ├── send: {"method":"tools/call","params":{"name":"read_file",...}}
  │                           └── return result
  │
  └── if check fails ──▶  ScopeError raised, MCP server never contacted
```

---

## 4. Pattern A: Agent wraps McpAdapter with scope enforcement

The simplest pattern. Each capability in your Agent maps to one MCP tool, with required scope declared upfront.

### Install

```bash
pip install agentpassport agentpassport-adapters
```

### Code

```python
# mcp_gated_agent.py
"""
An agentpassport Agent that gates MCP tool calls behind scope enforcement.
Each capability maps to a specific MCP tool.
Auth chain must be valid and grant the required scope before the tool runs.
"""

import asyncio
from agentpassport import Agent, TaskEnvelope, ScopeError
from agentpassport_adapters.mcp import McpAdapter

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

# The agentpassport agent that will receive tasks
agent = Agent("mcp-gateway")

# The MCP server to forward validated requests to
# Replace with your actual MCP server command
mcp = McpAdapter(command=["python", "-m", "my_mcp_server"])

# The orchestrator's DID and public key (established out-of-band)
# In production, load these from config/env
ORCHESTRATOR_DID = "did:key:z6Mk..."
ORCHESTRATOR_PUBKEY = bytes.fromhex("abc123...")

# Trust the orchestrator
agent.trust_keys({ORCHESTRATOR_DID: ORCHESTRATOR_PUBKEY})


# ---------------------------------------------------------------------------
# Capabilities — each maps to an MCP tool with a required scope
# ---------------------------------------------------------------------------

@agent.capability("read_file", requires=["fs:read"])
async def read_file(task: TaskEnvelope) -> dict:
    """Forward to MCP read_file tool. Requires fs:read in auth chain."""
    return await mcp.execute(task)


@agent.capability("write_file", requires=["fs:write"])
async def write_file(task: TaskEnvelope) -> dict:
    """Forward to MCP write_file tool. Requires fs:write in auth chain."""
    return await mcp.execute(task)


@agent.capability("execute_code", requires=["code:execute"])
async def execute_code(task: TaskEnvelope) -> dict:
    """Forward to MCP execute_code tool. Requires code:execute in auth chain."""
    return await mcp.execute(task)


@agent.capability("query_database", requires=["db:read"])
async def query_database(task: TaskEnvelope) -> dict:
    """Forward to MCP query_database tool. Requires db:read in auth chain."""
    return await mcp.execute(task)


# ---------------------------------------------------------------------------
# HTTP server to receive tasks
# ---------------------------------------------------------------------------

from fastapi import FastAPI, HTTPException, Request
import uvicorn

app = FastAPI()


@app.post("/task")
async def handle_task(request: Request):
    body = await request.json()
    task = TaskEnvelope(**body)
    try:
        result = await agent.handle(task)
        return result
    except ScopeError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Sending a task to it

```python
# send_task.py
import asyncio
import httpx
from agentpassport import Agent, TaskEnvelope, Intent, Constraints, sign_delegation, did_from_public_key, generate_keypair

# Orchestrator identity
private_key, public_key = generate_keypair()
orchestrator_did = did_from_public_key(public_key)

# MCP gateway agent's DID (get from the gateway at startup)
GATEWAY_DID = "did:key:z6Mk..."  # from the gateway's agent.did

# Build the task
task = TaskEnvelope(
    intent=Intent(type="read_file", params={"path": "/tmp/report.txt"}),
    constraints=Constraints(
        budget_credits=10,
        max_delegations=3,
        allowed_capabilities=["read_file"],
        denied_capabilities=[],
    ),
    auth_chain=[
        sign_delegation(
            issuer_private_key=private_key,
            issuer_did=orchestrator_did,
            subject_did=GATEWAY_DID,
            scope=["fs:read"],
            ttl_seconds=300,
        )
    ],
)

async def main():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/task",
            json=task.model_dump(mode="json"),
        )
        if resp.status_code == 403:
            print("Rejected:", resp.json()["detail"])
        else:
            print("Result:", resp.json())

asyncio.run(main())
```

---

## 5. Pattern B: HTTP proxy — enforce passport before forwarding to MCP server

If you have an existing MCP server accessible over HTTP (e.g., a server-sent events endpoint), you can run agentpassport as a proxy in front of it without modifying the MCP server at all.

```python
# mcp_proxy.py
"""
agentpassport HTTP proxy for an existing MCP server.

Incoming request:
  POST /tools/call
  Header: X-Auth-Chain: <jwt1>,<jwt2>,...
  Body: { "name": "read_file", "arguments": { "path": "..." } }

agentpassport:
1. Extracts auth chain from header
2. verify_auth_chain — signatures, linkage, narrowing, and final subject
3. TrustMiddleware.check — tool name → required scope
4. Forwards to backend MCP server if all checks pass
5. Returns 403 if either check fails
"""

import asyncio
import json
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from agentpassport import verify_auth_chain
from agentpassport.trust import TrustMiddleware, ScopeError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_MCP_URL = "http://localhost:9000"  # Your existing MCP server

# Map tool names to required agentpassport scopes
TOOL_SCOPE_MAP: dict[str, list[str]] = {
    "read_file":      ["fs:read"],
    "write_file":     ["fs:write"],
    "list_directory": ["fs:read"],
    "execute_bash":   ["code:execute"],
    "query_db":       ["db:read"],
    "write_db":       ["db:write"],
    # Tools with no required scope are publicly accessible
}

# Trusted issuer public keys
TRUSTED_KEYS: dict[str, bytes] = {
    "did:key:z6Mk...": bytes.fromhex("abc123..."),  # orchestrator
}

# Final JWT subject for this proxy. verify_auth_chain requires sub == PROXY_DID.
# TrustMiddleware.check does not compare the token subject to this DID.
PROXY_DID = "did:key:z6Mk..."

# ---------------------------------------------------------------------------
# Proxy implementation
# ---------------------------------------------------------------------------

app = FastAPI()


def check_auth(auth_chain_header: str | None, tool_name: str, proxy_did: str) -> None:
    """
    Verify auth chain from header and check scope for tool_name.
    Raises HTTPException(403) on any failure.
    """
    required_scope = TOOL_SCOPE_MAP.get(tool_name)
    if required_scope is None:
        return  # Tool has no scope requirement — allow through

    if not auth_chain_header:
        raise HTTPException(
            status_code=403,
            detail=f"Tool '{tool_name}' requires scope {required_scope!r} but no X-Auth-Chain header was provided."
        )

    # Parse comma-separated JWT list
    chain = [t.strip() for t in auth_chain_header.split(",") if t.strip()]
    if not chain:
        raise HTTPException(status_code=403, detail="X-Auth-Chain header is empty.")

    # Subject, chain linkage, and scope narrowing. TrustMiddleware.check does not do these.
    if not verify_auth_chain(
        auth_chain=chain,
        expected_subject=proxy_did,
        known_public_keys=TRUSTED_KEYS,
    ):
        raise HTTPException(status_code=403, detail="Auth chain verification failed.")

    # Tool scope only. A token whose subject is not proxy_did still passes this call.
    tm = TrustMiddleware(
        agent_did=proxy_did,
        known_public_keys=TRUSTED_KEYS,
        capability_scopes={tool_name: required_scope},
    )
    try:
        tm.check(chain, tool_name)
    except ScopeError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/tools/call")
async def proxy_tools_call(request: Request):
    body = await request.json()
    tool_name = body.get("name", "")
    auth_chain_header = request.headers.get("X-Auth-Chain")

    check_auth(auth_chain_header, tool_name, PROXY_DID)

    # Forward to backend MCP server
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BACKEND_MCP_URL}/tools/call",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

---

## 6. Pattern C: Inline middleware in your MCP server handler

If you control the MCP server source, you can enforce agentpassport inline using `TrustMiddleware` directly.

```python
# my_mcp_server.py
"""
MCP server with inline agentpassport trust enforcement.
Reads auth chain from a custom JSON-RPC 2.0 extension field: params._auth_chain
"""

import asyncio
import json
import sys
from agentpassport.trust import TrustMiddleware, ScopeError

# ---------------------------------------------------------------------------
# Trust configuration
# ---------------------------------------------------------------------------

TOOL_SCOPES: dict[str, list[str]] = {
    "read_file":   ["fs:read"],
    "write_file":  ["fs:write"],
    "run_query":   ["db:read"],
}

MY_DID = "did:key:z6Mk..."  # This server's agent DID
TRUSTED_KEYS: dict[str, bytes] = {
    "did:key:z6Mk...": bytes.fromhex("..."),  # known callers
}

trust = TrustMiddleware(
    agent_did=MY_DID,
    known_public_keys=TRUSTED_KEYS,
    capability_scopes=TOOL_SCOPES,
)

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def handle_read_file(arguments: dict) -> dict:
    path = arguments.get("path", "")
    # Read the file...
    return {"content": f"contents of {path}"}


async def handle_write_file(arguments: dict) -> dict:
    path = arguments.get("path", "")
    content = arguments.get("content", "")
    # Write the file...
    return {"written": True, "path": path, "bytes": len(content)}


async def handle_run_query(arguments: dict) -> dict:
    sql = arguments.get("sql", "")
    # Run query...
    return {"rows": [], "sql": sql}


TOOLS = {
    "read_file":  handle_read_file,
    "write_file": handle_write_file,
    "run_query":  handle_run_query,
}

# ---------------------------------------------------------------------------
# MCP stdio handler
# ---------------------------------------------------------------------------

async def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            print(json.dumps(response), flush=True)
            continue

        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if method != "tools/call":
            response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
            print(json.dumps(response), flush=True)
            continue

        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Extract auth chain from custom extension field
        auth_chain: list[str] = params.get("_auth_chain", [])

        # Trust check — runs before the tool handler
        try:
            trust.check(auth_chain, tool_name)
        except ScopeError as e:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e), "data": {"type": "ScopeError"}}
            }
            print(json.dumps(response), flush=True)
            continue

        # Dispatch to tool
        handler = TOOLS.get(tool_name)
        if handler is None:
            response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
            print(json.dumps(response), flush=True)
            continue

        try:
            result = await handler(arguments)
            response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}

        print(json.dumps(response), flush=True)


asyncio.run(main())
```

---

## 7. Scope design for MCP tools

There's no enforced naming convention — but a consistent scheme prevents confusion at scale.

### Recommended: `resource:action` or `resource:subresource:action`

| Tool | Recommended scope |
|------|-------------------|
| `read_file` | `fs:read` |
| `write_file` | `fs:write` |
| `list_directory` | `fs:read` |
| `delete_file` | `fs:delete` |
| `execute_bash` | `code:execute` |
| `query_database` | `db:read` |
| `write_database` | `db:write` |
| `send_email` | `email:send` |
| `read_email` | `email:read` |
| `call_stripe_api` | `api:stripe` |
| `call_openai_api` | `api:openai` |

### Grouping tools under a wildcard

If you want to grant access to all filesystem tools with a single scope string, use a broader scope and match it explicitly:

```python
# Capability declared as requiring "fs:read"
# Delegation grants "fs:*" — but agentpassport doesn't do glob matching by default

# Option 1: grant the exact scopes you need
scope=["fs:read", "fs:write", "fs:delete"]

# Option 2: grant "*" for full access (use sparingly — means everything)
scope=["*"]
```

agentpassport scope matching is **exact string match or `"*"` wildcard only**. There is no glob/prefix matching built in. If you need prefix matching (e.g., `fs:*` covers `fs:read`), implement it in your `TrustMiddleware` subclass.

---

## 8. Revocation mid-flight

Revoking a `jti` does not stop a running call. `verify_auth_chain(..., revocation_registry=registry)` returns false on the next check. Python `Agent.handle` and `TrustMiddleware.check` do not read the registry, so a later `handle` of the same task still succeeds unless you verify the chain yourself first.

```python
# revocation_demo.py
import asyncio
from agentpassport import (
    Agent, TaskEnvelope, Intent, Constraints,
    InMemoryRevocationRegistry,
    sign_delegation, did_from_public_key, generate_keypair,
    verify_auth_chain,
)
from agentpassport.identity.signing import _decode_jwt_claims

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

revocation_registry = InMemoryRevocationRegistry()

# Orchestrator
priv, pub = generate_keypair()
orchestrator_did = did_from_public_key(pub)

# MCP gateway agent. Its handle() checks scope, not the revocation registry.
gateway = Agent("mcp-gateway")
gateway.trust_keys({orchestrator_did: pub})


call_count = 0

@gateway.capability("read_file", requires=["fs:read"])
async def read_file(task: TaskEnvelope) -> dict:
    global call_count
    call_count += 1
    return {"content": "file data", "call": call_count}


# ---------------------------------------------------------------------------
# Demo: revoke mid-scenario
# ---------------------------------------------------------------------------

async def main():
    # Sign a delegation
    token = sign_delegation(
        issuer_private_key=priv,
        issuer_did=orchestrator_did,
        subject_did=gateway.did,
        scope=["fs:read"],
        ttl_seconds=3600,
    )

    # Extract the jti so we can revoke it later
    claims = _decode_jwt_claims(token)
    jti = claims["jti"]

    task = TaskEnvelope(
        intent=Intent(type="read_file", params={"path": "/tmp/data.csv"}),
        constraints=Constraints(budget_credits=10, max_delegations=3,
                                allowed_capabilities=[], denied_capabilities=[]),
        auth_chain=[token],
    )

    # Call 1 — succeeds
    result = await gateway.handle(task)
    print(f"Call 1: {result}")  # Call 1: {'content': 'file data', 'call': 1}

    # Revoke the token
    revocation_registry.revoke(jti)
    print(f"Revoked token: {jti[:8]}...")

    # Call 2 — verify_auth_chain with revocation registry now rejects it
    is_valid = verify_auth_chain(
        auth_chain=[token],
        expected_subject=gateway.did,
        known_public_keys={orchestrator_did: pub},
        revocation_registry=revocation_registry,
    )
    print(f"Chain valid after revocation: {is_valid}")  # False
    # gateway.handle(task) would still succeed. Check verify_auth_chain first.


asyncio.run(main())
```

---

## 9. Full runnable example

A complete system: Python orchestrator + agentpassport MCP gateway + a toy MCP file server.

```bash
# Install
pip install agentpassport agentpassport-adapters fastapi uvicorn httpx
```

```python
# full_mcp_demo.py
"""
Complete demo:
  1. A toy MCP file server (runs as subprocess)
  2. An agentpassport agent that gates calls to it
  3. An orchestrator that signs delegations and calls the agent

Run: python full_mcp_demo.py
"""

import asyncio
import json
import sys
import subprocess
import tempfile
import os
from agentpassport import (
    Agent, TaskEnvelope, Intent, Constraints, ScopeError,
    generate_keypair, did_from_public_key, sign_delegation,
)
from agentpassport_adapters.mcp import McpAdapter

# ---------------------------------------------------------------------------
# Toy MCP file server — written inline as a subprocess script
# ---------------------------------------------------------------------------

MCP_SERVER_SCRIPT = """
import json, sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except:
        continue

    tool = req.get("params", {}).get("name", "")
    args = req.get("params", {}).get("arguments", {})
    req_id = req.get("id")

    if tool == "read_file":
        path = args.get("path", "")
        try:
            with open(path) as f:
                content = f.read()
            result = {"content": content}
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}), flush=True)

    elif tool == "list_files":
        import os
        directory = args.get("directory", "/tmp")
        try:
            files = os.listdir(directory)
            result = {"files": files}
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}), flush=True)

    else:
        print(json.dumps({"jsonrpc": "2.0", "id": req_id,
                          "error": {"code": -32601, "message": f"Unknown tool: {tool}"}}), flush=True)
"""

# Write the MCP server script to a temp file
mcp_script = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
mcp_script.write(MCP_SERVER_SCRIPT)
mcp_script.flush()

# ---------------------------------------------------------------------------
# agentpassport gateway agent
# ---------------------------------------------------------------------------

gateway = Agent("mcp-gateway")
mcp = McpAdapter(command=[sys.executable, mcp_script.name])


@gateway.capability("read_file", requires=["fs:read"])
async def read_file(task: TaskEnvelope) -> dict:
    return await mcp.execute(task)


@gateway.capability("list_files", requires=["fs:read"])
async def list_files(task: TaskEnvelope) -> dict:
    return await mcp.execute(task)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def main():
    # Create a temp file to read
    test_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    test_file.write("Hello from agentpassport MCP demo!")
    test_file.flush()

    # Orchestrator identity
    priv, pub = generate_keypair()
    orch_did = did_from_public_key(pub)

    # Gateway trusts orchestrator
    gateway.trust_keys({orch_did: pub})

    def make_task(tool_name: str, params: dict, scope: list[str]) -> TaskEnvelope:
        token = sign_delegation(
            issuer_private_key=priv,
            issuer_did=orch_did,
            subject_did=gateway.did,
            scope=scope,
            ttl_seconds=300,
        )
        return TaskEnvelope(
            intent=Intent(type=tool_name, params=params),
            constraints=Constraints(budget_credits=10, max_delegations=2,
                                    allowed_capabilities=[], denied_capabilities=[]),
            auth_chain=[token],
        )

    print("=" * 60)
    print("  agentpassport MCP Demo")
    print("=" * 60)

    # Test 1: read_file with correct scope
    task = make_task("read_file", {"path": test_file.name}, scope=["fs:read"])
    result = await gateway.handle(task)
    print(f"\n[✅] read_file (scope=fs:read): {result}")

    # Test 2: list_files with correct scope
    task = make_task("list_files", {"directory": "/tmp"}, scope=["fs:read"])
    result = await gateway.handle(task)
    print(f"\n[✅] list_files (scope=fs:read): {len(result.get('files', []))} files in /tmp")

    # Test 3: read_file with wrong scope — rejected
    task = make_task("read_file", {"path": test_file.name}, scope=["db:read"])
    try:
        await gateway.handle(task)
    except ScopeError as e:
        print(f"\n[✅] read_file (scope=db:read) rejected: {e}")

    # Test 4: no auth chain — rejected
    task_no_auth = TaskEnvelope(
        intent=Intent(type="read_file", params={"path": test_file.name}),
        constraints=Constraints(budget_credits=10, max_delegations=2,
                                allowed_capabilities=[], denied_capabilities=[]),
        auth_chain=[],
    )
    try:
        await gateway.handle(task_no_auth)
    except ScopeError as e:
        print(f"\n[✅] read_file (no auth chain) rejected: {e}")

    print("\n" + "=" * 60)

    # Cleanup
    os.unlink(test_file.name)
    os.unlink(mcp_script.name)


asyncio.run(main())
```

Expected output:
```
============================================================
  agentpassport MCP Demo
============================================================

[✅] read_file (scope=fs:read): {'content': 'Hello from agentpassport MCP demo!'}

[✅] list_files (scope=fs:read): 12 files in /tmp

[✅] read_file (scope=db:read) rejected: Capability 'read_file' requires scope ['fs:read']
     not granted by the auth chain. Granted: ['db:read']

[✅] read_file (no auth chain) rejected: Capability 'read_file' requires scope ['fs:read']
     but the task carries no auth chain.

============================================================
```

---

## 10. Reference: McpAdapter

**Package:** `agentpassport-adapters`
**Module:** `agentpassport_adapters.mcp`

```python
class McpAdapter(Adapter):
    def __init__(self, command: list[str]) -> None
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]
```

### Constructor parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | `list[str]` | Yes | Subprocess command to launch the MCP server. Each element is a separate argument — do not pass a shell string. Example: `["python", "-m", "my_mcp_server"]` or `["npx", "my-mcp-server"]`. |

### `execute(task)` parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `task` | `TaskEnvelope` | The task to execute. `task.intent.type` becomes the MCP tool name. `task.intent.params` becomes the tool arguments. |

### Returns

`dict[str, Any]` — the `result` field from the MCP server's JSON-RPC 2.0 response.

### Raises

| Exception | When |
|-----------|------|
| `RuntimeError` | MCP server subprocess exits with non-zero return code. Message includes stderr. |
| `RuntimeError` | MCP server returns a response with an `"error"` key. Message includes the error object. |
| `json.JSONDecodeError` | MCP server returns non-JSON output on stdout. |

### JSON-RPC request structure

The request written to the MCP server's stdin:

```json
{
  "jsonrpc": "2.0",
  "id": "<task.id as string>",
  "method": "tools/call",
  "params": {
    "name": "<task.intent.type>",
    "arguments": { ...task.intent.params }
  }
}
```

**Note:** The auth chain is **not** forwarded to the MCP server. Trust enforcement happens in the agentpassport agent before `McpAdapter.execute()` is called. The MCP server sees only the tool call — it never needs to know about agentpassport.

### Performance note

`McpAdapter.execute()` launches a **fresh subprocess for each call** via `asyncio.create_subprocess_exec`. For MCP servers with negligible startup time (pure Python, no heavy imports) this is fine. For servers with significant startup cost:

- Keep a persistent subprocess and use a connection pool
- Use a long-running HTTP MCP server instead (Pattern B proxy)
- Use `asyncio.Lock` to serialize calls to a single persistent process
