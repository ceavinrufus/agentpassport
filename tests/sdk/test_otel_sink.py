from unittest.mock import MagicMock

from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.observability.otel import OtelSink
from agentpassport.types.events import ObservabilityEvent


def test_otel_sink_starts_span():
    """OtelSink.write() calls tracer.start_as_current_span with the event name."""
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    sink = OtelSink(tracer=mock_tracer)
    event = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_completed",
        agent=agent_did,
    )
    sink.write(event)

    mock_tracer.start_as_current_span.assert_called_once_with("agentpassport.task_completed")


def test_otel_sink_sets_agentpassport_attributes():
    """OtelSink sets trace_id, task_id, agent, cost_used as span attributes."""
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    sink = OtelSink(tracer=mock_tracer)
    event = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_running",
        agent=agent_did,
        cost_used=0.1,
        budget_remaining=0.9,
    )
    sink.write(event)

    mock_span.set_attribute.assert_any_call("agentpassport.trace_id", "trace_abc")
    mock_span.set_attribute.assert_any_call("agentpassport.task_id", "task_123")
    mock_span.set_attribute.assert_any_call("agentpassport.agent", agent_did)
    mock_span.set_attribute.assert_any_call("agentpassport.cost_used", 0.1)


def test_otel_sink_metadata_fan_out():
    """OtelSink fans out metadata dict as agentpassport.meta.<k> span attributes."""
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    sink = OtelSink(tracer=mock_tracer)
    event = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_running",
        agent=agent_did,
        metadata={"model": "gpt-4o", "retry": 2},
    )
    sink.write(event)

    mock_span.set_attribute.assert_any_call("agentpassport.meta.model", "gpt-4o")
    mock_span.set_attribute.assert_any_call("agentpassport.meta.retry", "2")
