from unittest.mock import MagicMock
from aps_sdk.types.events import ObservabilityEvent
from aps_sdk.observability.otel import OtelSink


def test_otel_sink_starts_span():
    """OtelSink.write() calls tracer.start_span with the event name."""
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_span.return_value.__exit__ = MagicMock(return_value=False)

    sink = OtelSink(tracer=mock_tracer)
    event = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_completed",
        agent="did:aps:xyz",
    )
    sink.write(event)

    mock_tracer.start_span.assert_called_once()
    assert "task_completed" in str(mock_tracer.start_span.call_args)


def test_otel_sink_sets_aps_attributes():
    """OtelSink sets trace_id, task_id, agent, cost_used as span attributes."""
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_span.return_value.__enter__ = MagicMock(return_value=mock_span)
    mock_tracer.start_span.return_value.__exit__ = MagicMock(return_value=False)

    sink = OtelSink(tracer=mock_tracer)
    event = ObservabilityEvent(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_running",
        agent="did:aps:xyz",
        cost_used=0.1,
        budget_remaining=0.9,
    )
    sink.write(event)

    mock_span.set_attribute.assert_any_call("aps.trace_id", "trace_abc")
    mock_span.set_attribute.assert_any_call("aps.task_id", "task_123")
    mock_span.set_attribute.assert_any_call("aps.agent", "did:aps:xyz")
    mock_span.set_attribute.assert_any_call("aps.cost_used", 0.1)
