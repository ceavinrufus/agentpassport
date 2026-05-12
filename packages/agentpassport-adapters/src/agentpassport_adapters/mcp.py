from __future__ import annotations

import asyncio
import json
from typing import Any

from agentpassport.types import TaskEnvelope

from agentpassport_adapters.base import Adapter


class McpAdapter(Adapter):
    """Adapter that wraps an MCP server (stdio transport)."""

    def __init__(self, command: list[str]) -> None:
        self.command = command

    async def execute(self, task: TaskEnvelope) -> dict[str, Any]:
        """Send a tool call to the MCP server via stdio."""
        request = {
            "jsonrpc": "2.0",
            "id": str(task.id),
            "method": "tools/call",
            "params": {
                "name": task.intent.type,
                "arguments": task.intent.params,
            },
        }

        proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        input_data = json.dumps(request).encode("utf-8") + b"\n"
        stdout, stderr = await proc.communicate(input=input_data)

        if proc.returncode != 0:
            raise RuntimeError(f"MCP server failed: {stderr.decode()}")

        response = json.loads(stdout.decode())
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response.get("result", {})
