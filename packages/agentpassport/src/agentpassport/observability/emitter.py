from __future__ import annotations

from agentpassport.observability.sinks import Sink
from agentpassport.types.events import ObservabilityEvent


class EventEmitter:
    def __init__(self, sinks: list[Sink] | None = None) -> None:
        self.sinks: list[Sink] = sinks or []

    def add_sink(self, sink: Sink) -> None:
        self.sinks.append(sink)

    def emit(
        self,
        trace_id: str,
        task_id: str,
        event: str,
        agent: str,
        **kwargs: object,
    ) -> None:
        evt = ObservabilityEvent(
            trace_id=trace_id,
            task_id=task_id,
            event=event,
            agent=agent,
            **kwargs,
        )
        for sink in self.sinks:
            sink.write(evt)

    def emit_state_change(
        self,
        trace_id: str,
        task_id: str,
        agent: str,
        from_state: str,
        to_state: str,
        cost_used: float = 0.0,
        budget_remaining: float = 0.0,
    ) -> None:
        self.emit(
            trace_id=trace_id,
            task_id=task_id,
            event="state_change",
            agent=agent,
            from_state=from_state,
            to_state=to_state,
            cost_used=cost_used,
            budget_remaining=budget_remaining,
        )
