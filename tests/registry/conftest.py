import pytest
from agentpassport_registry.limiter import limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory rate limit storage before every test."""
    # slowapi internals: _storage.reset() is not public API; pin slowapi<0.2 in pyproject.toml
    limiter._storage.reset()
    yield
