from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aps_sdk.identity.did import did_from_public_key, generate_keypair
from aps_sdk.identity.signing import sign_delegation
from aps_sdk.observability.emitter import EventEmitter
from aps_sdk.observability.sinks import StdoutSink
from aps_sdk.task.lifecycle import TaskLifecycle
from aps_sdk.transport.http import HttpTransport
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
        self._transport = HttpTransport()
        self.capabilities: dict[str, CapabilityHandler] = {}
        self._trusted_keys: dict[str, bytes] = {}
        self.emitter = emitter or EventEmitter(sinks=[StdoutSink()])

    def capability(self, name: str) -> Callable[[CapabilityHandler], CapabilityHandler]:
        """Decorator to register a capability handler."""

        def decorator(func: CapabilityHandler) -> CapabilityHandler:
            self.capabilities[name] = func
            return func

        return decorator

    def trust_keys(self, keys: dict[str, bytes]) -> None:
        """Register known public keys for auth chain verification."""
        self._trusted_keys.update(keys)

    async def delegate(
        self,
        task: TaskEnvelope,
        target_did: str,
        endpoint: str,
        scope: list[str] | None = None,
        ttl_seconds: int = 3600,
    ) -> dict:
        """Sign auth chain and send task to target agent."""
        entry = sign_delegation(
            issuer_private_key=self._private_key,
            issuer_did=self.did,
            subject_did=target_did,
            scope=scope or ["*"],
            ttl_seconds=ttl_seconds,
        )
        signed_task = task.model_copy(update={"auth_chain": [*task.auth_chain, entry]})
        return await self._transport.send(signed_task, endpoint)

    async def serve(
        self, host: str = "0.0.0.0", port: int = 8100, verify_auth: bool = False
    ) -> None:
        """Start HTTP server to receive tasks. Requires agentps[server] extra."""
        import uvicorn
        from aps_sdk.server import create_agent_app

        app = create_agent_app(self, verify_auth=verify_auth)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

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
