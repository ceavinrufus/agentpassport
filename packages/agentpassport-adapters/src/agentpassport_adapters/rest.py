from __future__ import annotations

import re
from typing import Any

import httpx
from agentpassport.types import TaskEnvelope

from agentpassport_adapters.base import Adapter


class RestAdapter(Adapter):
    def __init__(
        self,
        base_url: str,
        method: str = "POST",
        path: str = "/",
        body_template: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url
        self.method = method
        self.path = path
        self.body_template = body_template or {}
        self.headers = headers or {}

    def build_request(self, task: TaskEnvelope) -> dict[str, Any]:
        """Build the HTTP request from task params."""
        body = self._interpolate(self.body_template, task)
        return {
            "method": self.method,
            "url": f"{self.base_url}{self.path}",
            "body": body,
        }

    async def execute(self, task: TaskEnvelope) -> dict[str, Any]:
        req = self.build_request(task)
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=req["method"],
                url=req["url"],
                json=req["body"],
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    def _interpolate(self, template: dict[str, Any], task: TaskEnvelope) -> dict[str, Any]:
        """Replace {params.key} placeholders with actual values."""
        result: dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str):
                result[key] = re.sub(
                    r"\{params\.(\w+)\}",
                    lambda m: str(task.intent.params.get(m.group(1), "")),
                    value,
                )
            elif isinstance(value, dict):
                result[key] = self._interpolate(value, task)
            else:
                result[key] = value
        return result
