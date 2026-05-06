import pytest
from aps_sdk.task.retry import RetryExecutor
from aps_sdk.types.task import FailurePolicy


async def test_succeeds_on_second_attempt():
    """Retries on failure, returns result when callable eventually succeeds."""
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("transient")
        return {"ok": True}

    executor = RetryExecutor(FailurePolicy(retry=True, max_retries=3), base_delay=0.0)
    result = await executor.execute(flaky)
    assert result == {"ok": True}
    assert call_count == 2


async def test_raises_after_exhausting_retries():
    """Raises last exception after max_retries attempts."""

    async def always_fail():
        raise RuntimeError("permanent")

    executor = RetryExecutor(
        FailurePolicy(retry=True, max_retries=2, fallback="fail_hard"), base_delay=0.0
    )
    with pytest.raises(RuntimeError, match="permanent"):
        await executor.execute(always_fail)


async def test_no_retry_when_disabled():
    """Does not retry when policy.retry is False."""
    call_count = 0

    async def fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    executor = RetryExecutor(FailurePolicy(retry=False), base_delay=0.0)
    with pytest.raises(RuntimeError):
        await executor.execute(fail)
    assert call_count == 1


async def test_return_partial_fallback_returns_none():
    """When fallback is return_partial, returns None instead of raising."""

    async def always_fail():
        raise RuntimeError("fail")

    executor = RetryExecutor(
        FailurePolicy(retry=True, max_retries=1, fallback="return_partial"),
        base_delay=0.0,
    )
    result = await executor.execute(always_fail)
    assert result is None
