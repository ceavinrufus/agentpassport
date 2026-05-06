from __future__ import annotations

from typing import Any

import httpx

from aps_sdk.types.agent_card import AgentCard


class RegistryClient:
    """Client for the APS agent registry."""

    def __init__(self, registry_url: str, timeout: float = 10.0) -> None:
        self.registry_url = registry_url.rstrip("/")
        self.timeout = timeout

    async def discover(
        self,
        capability: str,
        max_cost: float | None = None,
        max_latency_ms: int | None = None,
    ) -> list[AgentCard]:
        """Find agents by capability, optionally filtered by cost/latency."""
        params: dict[str, Any] = {"capability": capability}
        if max_cost is not None:
            params["max_cost"] = max_cost
        if max_latency_ms is not None:
            params["max_latency_ms"] = max_latency_ms

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.registry_url}/v1/agents/query", params=params)
            resp.raise_for_status()

        return [AgentCard.model_validate(item) for item in resp.json()]

    async def publish(self, card: AgentCard) -> dict[str, str]:
        """Register an agent card with the registry."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.registry_url}/v1/agents",
                content=card.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        return resp.json()

    async def get(self, did: str) -> AgentCard | None:
        """Get a specific agent card by DID. Returns None if not found."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.registry_url}/v1/agents/{did}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        return AgentCard.model_validate(resp.json())
