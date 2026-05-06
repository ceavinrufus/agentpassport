import asyncio
import pytest
from aps_sdk.task.budget import BudgetTracker, BudgetExceededError


async def test_concurrent_spend_is_thread_safe():
    """10 concurrent async_spend(0.1) on 1.0 budget — no overspend."""
    tracker = BudgetTracker(total_credits=1.0)

    await asyncio.gather(*[tracker.async_spend(0.1) for _ in range(10)])
    assert tracker.remaining == pytest.approx(0.0, abs=1e-9)


async def test_concurrent_spend_rejects_overspend():
    """11 concurrent async_spend(0.1) on 1.0 budget — exactly 1 rejected."""
    tracker = BudgetTracker(total_credits=1.0)
    results = []

    async def try_spend():
        try:
            await tracker.async_spend(0.1)
            results.append("ok")
        except BudgetExceededError:
            results.append("rejected")

    await asyncio.gather(*[try_spend() for _ in range(11)])
    assert results.count("ok") == 10
    assert results.count("rejected") == 1


async def test_async_allocate_reserves_budget():
    """async_allocate returns the allocated amount and reduces remaining."""
    tracker = BudgetTracker(total_credits=5.0)
    amount = await tracker.async_allocate(3.0)
    assert amount == 3.0
    assert tracker.remaining == pytest.approx(2.0)


async def test_async_return_unused():
    """async_return_unused restores previously allocated budget."""
    tracker = BudgetTracker(total_credits=5.0)
    await tracker.async_allocate(3.0)
    await tracker.async_return_unused(1.0)
    assert tracker.remaining == pytest.approx(3.0)
