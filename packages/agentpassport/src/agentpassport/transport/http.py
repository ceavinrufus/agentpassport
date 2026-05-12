from __future__ import annotations

from typing import Any

import httpx

from agentpassport.transport.base import Transport
from agentpassport.types.task import TaskEnvelope


class HttpTransport(Transport):
    def __init__(self, base_url: str = "", timeout: float = 30.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def serialize(self, task: TaskEnvelope) -> bytes:
        return task.model_dump_json().encode("utf-8")

    def deserialize(self, data: bytes) -> TaskEnvelope:
        return TaskEnvelope.model_validate_json(data)

    async def send(self, task: TaskEnvelope, endpoint: str) -> dict[str, Any]:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{url}/agentpassport/tasks",
                content=self.serialize(task),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()
