import pytest
from aps_registry.limiter import limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory rate limit storage before every test."""
    limiter._storage.reset()
    yield
