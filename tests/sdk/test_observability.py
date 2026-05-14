from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.observability.emitter import EventEmitter
from agentpassport.observability.sinks import MemorySink


def test_emit_event_to_memory_sink():
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    sink = MemorySink()
    emitter = EventEmitter(sinks=[sink])

    emitter.emit(
        trace_id="trace_abc",
        task_id="task_123",
        event="task_created",
        agent=agent_did,
    )

    assert len(sink.events) == 1
    assert sink.events[0].event == "task_created"
    assert sink.events[0].trace_id == "trace_abc"


def test_emit_state_change():
    _, pub = generate_keypair()
    agent_did = did_from_public_key(pub)

    sink = MemorySink()
    emitter = EventEmitter(sinks=[sink])

    emitter.emit_state_change(
        trace_id="trace_abc",
        task_id="task_123",
        agent=agent_did,
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
