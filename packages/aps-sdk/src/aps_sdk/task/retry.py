from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aps_sdk.types.task import FailurePolicy


class RetryExecutor:
    """Execute async callables with retry logic per FailurePolicy."""

    def __init__(self, policy: FailurePolicy, base_delay: float = 1.0) -> None:
        self.policy = policy
        self.base_delay = base_delay

    async def execute(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        """Execute fn with retries. Returns result or handles fallback."""
        if not self.policy.retry:
            return await fn()

        last_error: Exception | None = None
        for attempt in range(1 + self.policy.max_retries):
            try:
                return await fn()
            except Exception as e:
                last_error = e
                if attempt < self.policy.max_retries and self.base_delay > 0:
                    await asyncio.sleep(self.base_delay * (2**attempt))

        if self.policy.fallback == "return_partial":
            return None
        raise last_error  # type: ignore[misc]
