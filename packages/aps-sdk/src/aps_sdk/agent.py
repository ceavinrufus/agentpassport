from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aps_sdk.identity.did import did_from_public_key, generate_keypair
from aps_sdk.observability.emitter import EventEmitter
from aps_sdk.observability.sinks import StdoutSink
from aps_sdk.task.lifecycle import TaskLifecycle
from aps_sdk.types.task import TaskEnvelope, TaskState

CapabilityHandler = Callable[[TaskEnvelope], Awaitable[dict[str, Any]]]


class Agent:
    def __init__(
        self,
        name: str,
        private_key: bytes | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self.name = name
        if private_key:
            from nacl.signing import SigningKey

            sk = SigningKey(private_key[:32])
            self._private_key = private_key
            self._public_key = bytes(sk.verify_key)
        else:
            self._private_key, self._public_key = generate_keypair()

        self.did = did_from_public_key(self._public_key)
        self.capabilities: dict[str, CapabilityHandler] = {}
        self.emitter = emitter or EventEmitter(sinks=[StdoutSink()])

    def capability(self, name: str) -> Callable[[CapabilityHandler], CapabilityHandler]:
        """Decorator to register a capability handler."""

        def decorator(func: CapabilityHandler) -> CapabilityHandler:
            self.capabilities[name] = func
            return func

        return decorator

    async def handle(self, task: TaskEnvelope) -> dict[str, Any]:
        """Handle an incoming task by dispatching to the registered capability handler."""
        handler = self.capabilities.get(task.intent.type)
        if handler is None:
            raise ValueError(f"No handler for capability: {task.intent.type}")

        trace_id = str(task.trace_id or task.id)
        task_id = str(task.id)

        lc = TaskLifecycle(task)
        lc.transition(TaskState.DELEGATED)
        lc.transition(TaskState.ACCEPTED)
        self.emitter.emit(trace_id=trace_id, task_id=task_id, event="task_accepted", agent=self.did)

        lc.transition(TaskState.RUNNING)
        self.emitter.emit(trace_id=trace_id, task_id=task_id, event="task_running", agent=self.did)

        try:
            result = await handler(task)
            lc.transition(TaskState.COMPLETED)
            self.emitter.emit(
                trace_id=trace_id, task_id=task_id, event="task_completed", agent=self.did
            )
            return result
        except Exception as e:
            lc.transition(TaskState.FAILED)
            self.emitter.emit(
                trace_id=trace_id,
                task_id=task_id,
                event="task_failed",
                agent=self.did,
                metadata={"error": str(e)},
            )
            raise
