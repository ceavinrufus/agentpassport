from __future__ import annotations

from aps_sdk.types import AgentCard


class QueryEngine:
    def query(
        self,
        cards: list[AgentCard],
        capability: str,
        max_cost_per_task: float | None = None,
        max_latency_ms: int | None = None,
    ) -> list[AgentCard]:
        """Filter and rank agent cards by capability, cost, and latency."""
        results = []
        for card in cards:
            if capability not in card.capabilities:
                continue
            if (
                max_cost_per_task is not None
                and card.cost is not None
                and card.cost.per_task > max_cost_per_task
            ):
                continue
            if (
                max_latency_ms is not None
                and card.latency_p99_ms is not None
                and card.latency_p99_ms > max_latency_ms
            ):
                continue
            results.append(card)

        # Rank by cost (cheapest first), then latency
        results.sort(
            key=lambda c: (c.cost.per_task if c.cost else float("inf"), c.latency_p99_ms or 0)
        )
        return results
