import pytest
from aps_sdk.transport.base import Transport
from aps_sdk.transport.http import HttpTransport
from aps_sdk.types import Intent, TaskEnvelope


def test_transport_is_abstract():
    with pytest.raises(TypeError):
        Transport()  # type: ignore


def test_http_transport_serializes_task():
    transport = HttpTransport(base_url="http://localhost:8000")
    task = TaskEnvelope(intent=Intent(type="search", params={"q": "hello"}))
    payload = transport.serialize(task)
    assert isinstance(payload, bytes)
    assert b"search" in payload
