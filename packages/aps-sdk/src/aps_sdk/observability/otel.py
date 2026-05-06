from __future__ import annotations

from typing import Any

from aps_sdk.observability.sinks import Sink
from aps_sdk.types.events import ObservabilityEvent


class OtelSink(Sink):
    """Exports ObservabilityEvents as OpenTelemetry spans."""

    def __init__(self, tracer: Any = None) -> None:
        if tracer is None:
            from opentelemetry import trace

            tracer = trace.get_tracer("aps-sdk")
        self._tracer = tracer

    def write(self, event: ObservabilityEvent) -> None:
        with self._tracer.start_span(f"aps.{event.event}") as span:
            span.set_attribute("aps.trace_id", event.trace_id)
            span.set_attribute("aps.task_id", event.task_id)
            span.set_attribute("aps.agent", event.agent)
            span.set_attribute("aps.event", event.event)
            span.set_attribute("aps.cost_used", event.cost_used)
            span.set_attribute("aps.budget_remaining", event.budget_remaining)
            if event.from_state:
                span.set_attribute("aps.from_state", event.from_state)
            if event.to_state:
                span.set_attribute("aps.to_state", event.to_state)
            for k, v in event.metadata.items():
                span.set_attribute(f"aps.meta.{k}", str(v))
