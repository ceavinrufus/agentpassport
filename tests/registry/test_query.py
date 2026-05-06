from aps_registry.query import QueryEngine
from aps_sdk.types import AgentCard, CostInfo


def _cards():
    return [
        AgentCard(
            did="did:aps:fast-search",
            name="Fast Search",
            capabilities=["search"],
            endpoint="http://a",
            cost=CostInfo(per_task=0.02),
            latency_p99_ms=200,
        ),
        AgentCard(
            did="did:aps:cheap-search",
            name="Cheap Search",
            capabilities=["search", "summarize"],
            endpoint="http://b",
            cost=CostInfo(per_task=0.005),
            latency_p99_ms=1000,
        ),
        AgentCard(
            did="did:aps:writer",
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
    assert results[0].did == "did:aps:cheap-search"


def test_query_with_latency_filter():
    engine = QueryEngine()
    results = engine.query(_cards(), capability="search", max_latency_ms=500)
    assert len(results) == 1
    assert results[0].did == "did:aps:fast-search"


def test_query_no_match():
    engine = QueryEngine()
    results = engine.query(_cards(), capability="translate")
    assert len(results) == 0
