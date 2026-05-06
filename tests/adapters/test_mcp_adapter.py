import sys

import pytest

from aps_adapters.mcp import McpAdapter
from aps_sdk.types import TaskEnvelope
from aps_sdk.types.task import Intent


def test_mcp_adapter_instantiable():
    adapter = McpAdapter(command=["echo"])
    assert adapter.command == ["echo"]


# ---------------------------------------------------------------------------
# Integration tests – real subprocesses, no mocking
# ---------------------------------------------------------------------------

_TOOL_CALL_SERVER = (
    "import sys, json; "
    "req = json.loads(sys.stdin.readline()); "
    'sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"], '
    '"result": {"content": [{"type": "text", "text": "42"}]}}) + "\\n"); '
    "sys.stdout.flush()"
)

_ERROR_SERVER = (
    "import sys, json; "
    "req = json.loads(sys.stdin.readline()); "
    'sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"], '
    '"error": {"code": -32000, "message": "tool not found"}}) + "\\n"); '
    "sys.stdout.flush()"
)

_CRASH_SERVER = "import sys; sys.exit(1)"


def _make_task() -> TaskEnvelope:
    return TaskEnvelope(intent=Intent(type="echo", params={"msg": "hello"}))


@pytest.mark.asyncio
async def test_mcp_adapter_tool_call():
    adapter = McpAdapter(command=[sys.executable, "-c", _TOOL_CALL_SERVER])
    result = await adapter.execute(_make_task())
    assert result == {"content": [{"type": "text", "text": "42"}]}


@pytest.mark.asyncio
async def test_mcp_adapter_error_propagation():
    adapter = McpAdapter(command=[sys.executable, "-c", _ERROR_SERVER])
    with pytest.raises(RuntimeError, match="MCP error"):
        await adapter.execute(_make_task())


@pytest.mark.asyncio
async def test_mcp_adapter_server_crash():
    adapter = McpAdapter(command=[sys.executable, "-c", _CRASH_SERVER])
    with pytest.raises(RuntimeError, match="MCP server failed"):
        await adapter.execute(_make_task())
