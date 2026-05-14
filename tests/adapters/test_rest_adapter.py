import pytest
from agentpassport.types import Intent, TaskEnvelope
from agentpassport_adapters.base import Adapter
from agentpassport_adapters.rest import RestAdapter


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        Adapter()  # type: ignore


async def test_rest_adapter_builds_request():
    adapter = RestAdapter(
        base_url="http://api.example.com",
        method="POST",
        path="/search",
        body_template={"query": "{params.q}"},
    )
    task = TaskEnvelope(intent=Intent(type="search", params={"q": "hello"}))
    request = adapter.build_request(task)
    assert request["method"] == "POST"
    assert request["url"] == "http://api.example.com/search"
    assert request["body"]["query"] == "hello"
