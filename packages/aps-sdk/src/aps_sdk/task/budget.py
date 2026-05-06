from __future__ import annotations

import asyncio


class BudgetExceededError(Exception):
    def __init__(self, requested: float, remaining: float):
        super().__init__(f"Budget exceeded: requested {requested}, remaining {remaining}")
        self.requested = requested
        self.remaining = remaining


class BudgetTracker:
    def __init__(self, total_credits: float):
        self.total_credits = total_credits
        self.spent: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def remaining(self) -> float:
        return self.total_credits - self.spent

    def spend(self, amount: float) -> None:
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        if amount > self.remaining:
            raise BudgetExceededError(requested=amount, remaining=self.remaining)
        self.spent += amount

    def allocate(self, amount: float) -> float:
        """Reserve budget for a subtask. Returns the allocated amount."""
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        if amount > self.remaining:
            raise BudgetExceededError(requested=amount, remaining=self.remaining)
        self.spent += amount
        return amount

    def return_unused(self, amount: float) -> None:
        """Return unused budget from a completed subtask."""
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        self.spent = max(0.0, self.spent - amount)

    async def async_spend(self, amount: float) -> None:
        """Thread-safe spend under asyncio lock."""
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        async with self._lock:
            if amount > self.remaining:
                raise BudgetExceededError(requested=amount, remaining=self.remaining)
            self.spent += amount

    async def async_allocate(self, amount: float) -> float:
        """Thread-safe allocate under asyncio lock. Returns allocated amount."""
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        async with self._lock:
            if amount > self.remaining:
                raise BudgetExceededError(requested=amount, remaining=self.remaining)
            self.spent += amount
            return amount

    async def async_return_unused(self, amount: float) -> None:
        """Thread-safe return_unused under asyncio lock."""
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")
        async with self._lock:
            self.spent = max(0.0, self.spent - amount)
