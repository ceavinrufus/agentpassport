from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.types import AgentCard, CostInfo
from agentpassport_registry.query import QueryEngine


def _make_did():
    _, pub = generate_keypair()
    return did_from_public_key(pub)


# Generate stable DIDs once at module level so assertion values are consistent
# within a single test run.
_DID_FAST_SEARCH = _make_did()
_DID_CHEAP_SEARCH = _make_did()
_DID_WRITER = _make_did()


def _cards():
    return [
        AgentCard(
            did=_DID_FAST_SEARCH,
            name="Fast Search",
            capabilities=["search"],
            endpoint="http://a",
            cost=CostInfo(per_task=0.02),
            latency_p99_ms=200,
        ),
        AgentCard(
            did=_DID_CHEAP_SEARCH,
            name="Cheap Search",
            capabilities=["search", "summarize"],
            endpoint="http://b",
            cost=CostInfo(per_task=0.005),
            latency_p99_ms=1000,
        ),
        AgentCard(
            did=_DID_WRITER,
            name="Writer",
            capabilities=["write"],
            endpoint="http://c",
            cost=CostInfo(per_task=0.1),
            latency_p99_ms=3000,
        ),
    ]


def test_query_by_capability():
    engine = QueryEngine()
    results = engine.query(_cards(), capability="search")
    assert len(results) == 2
    assert all("search" in c.capabilities for c in results)


def test_query_with_budget_filter():
    engine = QueryEngine()
    results = engine.query(_cards(), capability="search", max_cost_per_task=0.01)
    assert len(results) == 1
    assert results[0].did == _DID_CHEAP_SEARCH


def test_query_with_latency_filter():
    engine = QueryEngine()
    results = engine.query(_cards(), capability="search", max_latency_ms=500)
    assert len(results) == 1
    assert results[0].did == _DID_FAST_SEARCH


def test_query_no_match():
    engine = QueryEngine()
    results = engine.query(_cards(), capability="translate")
    assert len(results) == 0
