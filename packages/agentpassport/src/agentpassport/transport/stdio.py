from __future__ import annotations

import asyncio
import json
from typing import Any

from agentpassport.transport.base import Transport
from agentpassport.types.task import TaskEnvelope


class StdioTransport(Transport):
    """Transport for local subprocess communication via stdin/stdout."""

    def __init__(self, command: list[str]) -> None:
        self.command = command

    def serialize(self, task: TaskEnvelope) -> bytes:
        return task.model_dump_json().encode("utf-8") + b"\n"

    def deserialize(self, data: bytes) -> TaskEnvelope:
        return TaskEnvelope.model_validate_json(data)

    async def send(self, task: TaskEnvelope, endpoint: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=self.serialize(task))
        if proc.returncode != 0:
            raise RuntimeError(f"Subprocess failed: {stderr.decode()}")
        return json.loads(stdout.decode())
