from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.identity.signing import sign_delegation
from agentpassport.observability.emitter import EventEmitter
from agentpassport.observability.sinks import StdoutSink
from agentpassport.task.lifecycle import TaskLifecycle
from agentpassport.transport.http import HttpTransport
from agentpassport.trust import ScopeError, TrustMiddleware
from agentpassport.types.task import TaskEnvelope, TaskState

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
        self._capability_scopes: dict[str, list[str]] = {}
        self._trusted_keys: dict[str, bytes] = {}
        self.emitter = emitter or EventEmitter(sinks=[StdoutSink()])
        self._trust_middleware = TrustMiddleware(
            agent_did=self.did,
            known_public_keys=self._trusted_keys,
            capability_scopes=self._capability_scopes,
        )

    def capability(
        self,
        name: str,
        requires: list[str] | None = None,
    ) -> Callable[[CapabilityHandler], CapabilityHandler]:
        """Decorator to register a capability handler.

        Args:
            name:     Capability name matched against task.intent.type.
            requires: Optional list of scope strings (action:resource) that the
                      incoming task's auth chain must grant before the handler
                      runs. If omitted or empty, no scope check is performed.
                      Example: requires=["read:db:customers"]
        """

        def decorator(func: CapabilityHandler) -> CapabilityHandler:
            self.capabilities[name] = func
            if requires:
                self._capability_scopes[name] = requires
            return func

        return decorator

    @property
    def public_key(self) -> bytes:
        """The agent's Ed25519 public key (32 bytes)."""
        return self._public_key

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

    async def handle(self, task: TaskEnvelope) -> dict[str, Any]:
        """Handle an incoming task by dispatching to the registered capability handler.

        Pre-execution scope check runs automatically if the capability
        declares requires=[...]. ScopeError is raised before the handler
        is called if the auth chain does not cover the declared scope.
        """
        handler = self.capabilities.get(task.intent.type)
        if handler is None:
            raise ValueError(f"No handler for capability: {task.intent.type}")

        # Pre-execution scope declaration check — raises ScopeError if violated
        self._trust_middleware.check(task.auth_chain, task.intent.type)

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
