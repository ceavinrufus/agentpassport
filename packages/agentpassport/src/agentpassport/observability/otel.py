from __future__ import annotations

from typing import Any

from agentpassport.observability.sinks import Sink
from agentpassport.types.events import ObservabilityEvent


class OtelSink(Sink):
    """Exports ObservabilityEvents as OpenTelemetry spans."""

    def __init__(self, tracer: Any = None) -> None:
        if tracer is None:
            try:
                from opentelemetry import trace
                from opentelemetry.trace import NonRecordingSpan  # noqa: F401
            except ImportError as e:
                raise ImportError(
                    "opentelemetry-api is required for OtelSink. "
                    "Install with: pip install agentpassport[otel]"
                ) from e

            tracer = trace.get_tracer("agentpassport")
        self._tracer = tracer

    def write(self, event: ObservabilityEvent) -> None:
        try:
            with self._tracer.start_as_current_span(f"agentpassport.{event.event}") as span:
                span.set_attribute("agentpassport.trace_id", event.trace_id)
                span.set_attribute("agentpassport.task_id", event.task_id)
                span.set_attribute("agentpassport.agent", event.agent)
                span.set_attribute("agentpassport.event", event.event)
                span.set_attribute("agentpassport.cost_used", event.cost_used)
                span.set_attribute("agentpassport.budget_remaining", event.budget_remaining)
                if event.from_state:
                    span.set_attribute("agentpassport.from_state", event.from_state)
                if event.to_state:
                    span.set_attribute("agentpassport.to_state", event.to_state)
                for k, v in event.metadata.items():
                    span.set_attribute(f"agentpassport.meta.{k}", str(v))
        except Exception:
            pass  # don't let observability failures crash the agent
