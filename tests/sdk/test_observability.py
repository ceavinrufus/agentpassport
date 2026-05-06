from aps_sdk.observability.emitter import EventEmitter
from aps_sdk.observability.sinks import MemorySink


def test_emit_event_to_memory_sink():
    sink = MemorySink()
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_created",
        agent="did:aps:test",
    )

    assert len(sink.events) == 1
    assert sink.events[0].event == "task_created"
    assert sink.events[0].trace_id == "trace_abc"


def test_emit_state_change():
    sink = MemorySink()
    emitter = EventEmitter(sinks=[sink])

    emitter.emit_state_change(
        trace_id="trace_abc",
        task_id="task_123",
        agent="did:aps:test",
        from_state="created",
        to_state="delegated",
        cost_used=1.0,
        budget_remaining=9.0,
    )

    evt = sink.events[0]
    assert evt.event == "state_change"
    assert evt.from_state == "created"
    assert evt.to_state == "delegated"
    assert evt.cost_used == 1.0
