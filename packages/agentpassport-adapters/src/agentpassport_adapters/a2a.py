"""A2A protocol adapters for agentpassport.

This module provides two adapters:

* :class:`A2AServerAdapter` — exposes an agentpassport :class:`~agentpassport.agent.Agent`
  as an A2A-compliant HTTP server.  Mount the Starlette app returned by
  :meth:`A2AServerAdapter.build_app` to serve A2A traffic.

* :class:`A2AClientAdapter` — wraps a remote A2A agent as an agentpassport
  :class:`~agentpassport_adapters.base.Adapter`, letting agentpassport agents
  delegate tasks to external A2A agents.

The module also exposes :func:`synthesize_a2a_agent_card`, a utility that
converts an agentpassport :class:`~agentpassport.types.AgentCard` to the A2A
wire format dict.

**a2a-sdk dependency is optional.**  When the ``a2a`` package is present its
protobuf types and JSON helpers are used for correct serialisation.  When it is
absent the adapter falls back to a minimal hand-rolled implementation that
speaks the same JSON-RPC 2.0 wire format.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from agentpassport.agent import Agent
from agentpassport.trust import ScopeError
from agentpassport.types import AgentCard as APSAgentCard, Intent, TaskEnvelope

from agentpassport_adapters.base import Adapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional a2a-sdk import
# ---------------------------------------------------------------------------
try:
    from google.protobuf.json_format import MessageToDict, ParseDict
    from a2a.types.a2a_pb2 import (
        AgentCard as A2AAgentCard,
        AgentCapabilities,
        AgentInterface,
        AgentSkill,
        Message as A2AMessage,
        Part as A2APart,
        ROLE_AGENT,
        ROLE_USER,
        SendMessageRequest,
        Task as A2ATask,
        TASK_STATE_CANCELED,
        TASK_STATE_COMPLETED,
        TASK_STATE_FAILED,
        TASK_STATE_SUBMITTED,
        TASK_STATE_WORKING,
    )

    _A2A_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _A2A_SDK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Auth-chain header name
# ---------------------------------------------------------------------------
_AUTH_CHAIN_HEADER = "X-AgentPassport-Auth-Chain"

# JSON-RPC error codes
_JSONRPC_INTERNAL_ERROR = -32603
_JSONRPC_INVALID_PARAMS = -32602
_JSONRPC_METHOD_NOT_FOUND = -32601

# Terminal A2A task states (string values used in fallback mode)
_TERMINAL_STATES = frozenset(
    {
        "TASK_STATE_COMPLETED",
        "TASK_STATE_FAILED",
        "TASK_STATE_CANCELED",
        "TASK_STATE_REJECTED",
        "TASK_STATE_AUTH_REQUIRED",
    }
)


# ---------------------------------------------------------------------------
# AgentCard synthesis utility
# ---------------------------------------------------------------------------


def synthesize_a2a_agent_card(
    aps_card: APSAgentCard,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Convert an agentpassport :class:`AgentCard` to an A2A AgentCard dict.

    The resulting dict conforms to the A2A 1.0 AgentCard wire format and can
    be serialised directly to JSON for the ``/.well-known/agent-card.json``
    endpoint.

    Agentpassport-specific fields (``did``, ``signature``) are carried in
    extension fields prefixed with ``x_agentpassport_``.

    Args:
        aps_card: The agentpassport AgentCard to convert.
        endpoint: Override the endpoint URL in the resulting A2A card.
                  Defaults to ``aps_card.endpoint`` when not provided.

    Returns:
        A dict ready for ``json.dumps`` that represents the A2A AgentCard.
    """
    effective_endpoint = endpoint or aps_card.endpoint

    skills: list[dict[str, Any]] = [
        {"id": cap, "name": cap}
        for cap in aps_card.capabilities
    ]

    supported_interfaces: list[dict[str, Any]] = []
    if effective_endpoint:
        supported_interfaces.append({"url": effective_endpoint})

    card: dict[str, Any] = {
        "name": aps_card.name,
        "description": "",
        "skills": skills,
        "supportedInterfaces": supported_interfaces,
        # agentpassport extensions
        "x_agentpassport_did": aps_card.did,
    }

    if aps_card.signature is not None:
        card["x_agentpassport_signature"] = aps_card.signature

    if _A2A_SDK_AVAILABLE:
        # Use the SDK to build a proper protobuf-backed dict for perfect fidelity
        proto_card = A2AAgentCard()
        proto_card.name = aps_card.name
        for cap in aps_card.capabilities:
            skill = proto_card.skills.add()
            skill.id = cap
            skill.name = cap
        if effective_endpoint:
            iface = proto_card.supported_interfaces.add()
            iface.url = effective_endpoint
        card = MessageToDict(proto_card)
        # Overlay agentpassport extensions (not present in proto schema)
        card["x_agentpassport_did"] = aps_card.did
        if aps_card.signature is not None:
            card["x_agentpassport_signature"] = aps_card.signature

    return card


# ---------------------------------------------------------------------------
# Helper: build A2A Task response dict
# ---------------------------------------------------------------------------


def _build_a2a_task(
    task_id: str,
    state_str: str,
    result_text: str,
) -> dict[str, Any]:
    """Build a minimal A2A Task response dict.

    Args:
        task_id:    The A2A task identifier.
        state_str:  One of the ``TASK_STATE_*`` string values.
        result_text: A human-readable result or error message.

    Returns:
        A dict suitable for embedding in a JSON-RPC result.
    """
    if _A2A_SDK_AVAILABLE:
        task = A2ATask()
        task.id = task_id
        state_map = {
            "TASK_STATE_SUBMITTED": TASK_STATE_SUBMITTED,
            "TASK_STATE_WORKING": TASK_STATE_WORKING,
            "TASK_STATE_COMPLETED": TASK_STATE_COMPLETED,
            "TASK_STATE_FAILED": TASK_STATE_FAILED,
        }
        task.status.state = state_map.get(state_str, TASK_STATE_FAILED)
        status_msg = task.status.message
        status_msg.message_id = str(uuid.uuid4())
        status_msg.role = ROLE_AGENT
        part = status_msg.parts.add()
        part.text = result_text
        return MessageToDict(task)

    # Fallback: hand-rolled dict
    return {
        "id": task_id,
        "status": {
            "state": state_str,
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_AGENT",
                "parts": [{"text": result_text}],
            },
        },
    }


def _extract_text_from_a2a_message(message: dict[str, Any]) -> str:
    """Extract the concatenated text content from an A2A Message dict.

    Walks all parts and joins ``text`` fields.

    Args:
        message: An A2A Message as a plain dict.

    Returns:
        Concatenated text from all text parts, or an empty string.
    """
    parts = message.get("parts", [])
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
    return "\n".join(t for t in texts if t)


# ---------------------------------------------------------------------------
# Pattern B — A2AServerAdapter (inbound)
# ---------------------------------------------------------------------------


class A2AServerAdapter:
    """Expose an agentpassport :class:`~agentpassport.agent.Agent` as an A2A server.

    The adapter creates a Starlette application that:

    * Serves ``/.well-known/agent-card.json`` synthesised from the agent's
      :class:`~agentpassport.types.AgentCard`.
    * Handles the ``message/send`` JSON-RPC 2.0 method at the root path.
    * Extracts the agentpassport auth chain from the
      ``X-AgentPassport-Auth-Chain`` header (comma-separated JWTs) and
      attaches it to the :class:`~agentpassport.types.TaskEnvelope`.
    * Maps A2A skill ids to agentpassport capability names (1-to-1 by
      default, overrideable via ``skill_map``).
    * Converts :class:`~agentpassport.trust.ScopeError` to a structured
      A2A error response instead of a 500.

    Args:
        agent: The agentpassport Agent to wrap.
        agent_card: Pre-built AgentCard for this agent.  When omitted the
            adapter calls ``agent.card`` (requires the ``card`` property to
            exist on the Agent).
        endpoint: The public HTTP endpoint URL for this server.  Used in
            the synthesised A2A AgentCard.
        skill_map: Optional ``{a2a_skill_id: aps_capability_name}`` mapping.
            When provided, incoming A2A skill ids are translated before
            dispatching to the Agent.  By default skill id == capability name.

    Example::

        server = A2AServerAdapter(agent=my_agent, agent_card=card, endpoint="http://…")
        app = server.build_app()
        # mount `app` with uvicorn/starlette
    """

    def __init__(
        self,
        agent: Agent,
        agent_card: APSAgentCard | None = None,
        endpoint: str = "",
        skill_map: dict[str, str] | None = None,
    ) -> None:
        self._agent = agent
        self._agent_card: APSAgentCard | None = agent_card
        self._endpoint = endpoint
        self._skill_map: dict[str, str] = skill_map or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_app(self) -> Any:
        """Build and return a Starlette application.

        The returned app responds to:

        * ``GET /.well-known/agent-card.json`` — A2A AgentCard discovery
        * ``POST /`` — JSON-RPC 2.0 endpoint for ``message/send``

        Returns:
            A ``starlette.applications.Starlette`` instance.

        Raises:
            ImportError: If Starlette is not installed.
        """
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import JSONResponse, Response
            from starlette.routing import Route
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Starlette is required to build an A2AServerAdapter app. "
                "Install it with: pip install starlette"
            ) from exc

        async def agent_card_handler(request: Request) -> Response:
            return JSONResponse(self._get_a2a_card())

        async def jsonrpc_handler(request: Request) -> Response:
            return await self._handle_jsonrpc(request, JSONResponse)

        routes = [
            Route("/.well-known/agent-card.json", agent_card_handler, methods=["GET"]),
            Route("/", jsonrpc_handler, methods=["POST"]),
        ]
        return Starlette(routes=routes)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_aps_card(self) -> APSAgentCard:
        """Return the agentpassport AgentCard, falling back to agent.card."""
        if self._agent_card is not None:
            return self._agent_card
        # Try agent.card property (added in this PR)
        card: APSAgentCard | None = getattr(self._agent, "card", None)
        if card is None:
            raise RuntimeError(
                "A2AServerAdapter requires an AgentCard.  Either pass agent_card= "
                "to the constructor, or ensure agent.card is available."
            )
        return card

    def _get_a2a_card(self) -> dict[str, Any]:
        """Return the A2A AgentCard dict for this agent."""
        aps_card = self._get_aps_card()
        return synthesize_a2a_agent_card(aps_card, endpoint=self._endpoint or None)

    def _resolve_capability(self, skill_id: str) -> str:
        """Map an A2A skill id to an agentpassport capability name.

        Uses ``skill_map`` if provided; falls back to identity mapping.

        Args:
            skill_id: The A2A skill identifier from the incoming request.

        Returns:
            The agentpassport capability name to dispatch to.
        """
        return self._skill_map.get(skill_id, skill_id)

    def _parse_auth_chain(self, raw_header: str | None) -> list[str]:
        """Parse the comma-separated JWT auth-chain header.

        Args:
            raw_header: The raw ``X-AgentPassport-Auth-Chain`` header value,
                or ``None`` if the header was not present.

        Returns:
            A list of JWT strings.  Empty list when header is absent or empty.
        """
        if not raw_header:
            return []
        return [token.strip() for token in raw_header.split(",") if token.strip()]

    async def _handle_jsonrpc(
        self,
        request: Any,
        JSONResponse: type,
    ) -> Any:
        """Dispatch a JSON-RPC 2.0 request to the wrapped agent.

        Supports the ``message/send`` method only.  All other methods return a
        ``MethodNotFound`` error response.

        Args:
            request:      The Starlette Request object.
            JSONResponse: The Starlette JSONResponse class (passed in to avoid
                          re-importing inside the handler).

        Returns:
            A JSONResponse with either a JSON-RPC result or error.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                _jsonrpc_error(None, _JSONRPC_INTERNAL_ERROR, "Parse error: request body is not valid JSON"),
                status_code=400,
            )

        rpc_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {})

        if method not in ("message/send", "SendMessage"):
            return JSONResponse(
                _jsonrpc_error(rpc_id, _JSONRPC_METHOD_NOT_FOUND, f"Method '{method}' not found.  This server supports: message/send"),
            )

        # Extract message from params
        message_dict: dict[str, Any] = params.get("message", params)
        # metadata can be a nested object within the message
        metadata: dict[str, Any] = message_dict.get("metadata", {}) or {}
        skill_id: str = (
            message_dict.get("skillId")
            or message_dict.get("skill_id")
            or metadata.get("skillId")
            or metadata.get("skill_id")
            or ""
        )
        text_input = _extract_text_from_a2a_message(message_dict)
        # Also collect structured params from metadata (already extracted above)

        # Map skill → capability
        capability = self._resolve_capability(skill_id) if skill_id else ""
        if not capability:
            # Try to infer from first registered capability when no skill
            registered = list(self._agent.capabilities.keys())
            if len(registered) == 1:
                capability = registered[0]
            elif registered:
                return JSONResponse(
                    _jsonrpc_error(
                        rpc_id,
                        _JSONRPC_INVALID_PARAMS,
                        f"No skill id provided and agent has multiple capabilities {registered!r}.  "
                        "Set skillId in the message.",
                    )
                )
            else:
                return JSONResponse(
                    _jsonrpc_error(rpc_id, _JSONRPC_INVALID_PARAMS, "No capabilities registered on this agent.")
                )

        if capability not in self._agent.capabilities:
            registered = list(self._agent.capabilities.keys())
            return JSONResponse(
                _jsonrpc_error(
                    rpc_id,
                    _JSONRPC_INVALID_PARAMS,
                    f"Unknown skill '{skill_id}' (resolved capability: '{capability}').  "
                    f"Registered capabilities: {registered!r}",
                )
            )

        # Build auth chain
        auth_chain = self._parse_auth_chain(
            request.headers.get(_AUTH_CHAIN_HEADER)
        )

        # Build TaskEnvelope
        intent_params: dict[str, Any] = dict(metadata)
        if text_input:
            intent_params["text"] = text_input
        task_id = str(uuid.uuid4())
        envelope = TaskEnvelope(
            id=task_id,
            intent=Intent(type=capability, params=intent_params),
            auth_chain=auth_chain,
        )

        # Dispatch
        try:
            result = await self._agent.handle(envelope)
        except ScopeError as exc:
            logger.info("A2A request denied by scope check: %s", exc)
            return JSONResponse(
                _jsonrpc_error(
                    rpc_id,
                    -32000,  # Server-defined application error
                    f"Authorization denied: {exc}",
                )
            )
        except ValueError as exc:
            # e.g. no handler for capability (shouldn't reach here after our check)
            return JSONResponse(
                _jsonrpc_error(rpc_id, _JSONRPC_INVALID_PARAMS, str(exc))
            )
        except Exception as exc:
            logger.exception("A2A handler raised unexpected exception")
            return JSONResponse(
                _jsonrpc_error(rpc_id, _JSONRPC_INTERNAL_ERROR, f"Internal error: {exc}")
            )

        # Serialise result dict → A2A Task
        result_text = json.dumps(result) if not isinstance(result, str) else result
        a2a_task = _build_a2a_task(task_id, "TASK_STATE_COMPLETED", result_text)

        return JSONResponse(
            {"jsonrpc": "2.0", "id": rpc_id, "result": {"task": a2a_task}}
        )


# ---------------------------------------------------------------------------
# Pattern A — A2AClientAdapter (outbound)
# ---------------------------------------------------------------------------


class A2AClientAdapter(Adapter):
    """Delegate tasks to a remote A2A agent.

    Implements the agentpassport :class:`~agentpassport_adapters.base.Adapter`
    ABC, allowing agentpassport agents to call out to any A2A-compliant
    service.

    The adapter:

    * Fetches and caches the remote agent's AgentCard from
      ``agent_card_url`` (``/.well-known/agent-card.json``).
    * Translates a :class:`~agentpassport.types.TaskEnvelope` into an A2A
      ``message/send`` JSON-RPC 2.0 request.
    * Injects the agentpassport auth chain into the ``X-AgentPassport-Auth-Chain``
      request header when ``task.auth_chain`` is non-empty.
    * Polls the remote agent until the task reaches a terminal state.
    * Raises :class:`TimeoutError` if the task does not complete within
      ``timeout`` seconds.

    When the ``a2a-sdk`` package is installed its types are used; otherwise the
    adapter falls back to hand-rolled httpx calls with the same wire protocol.

    Args:
        agent_card_url: Full URL to the remote agent's AgentCard endpoint,
            typically ``https://host/.well-known/agent-card.json``.
        auth_token:     Optional Bearer token for authenticating with the
            remote A2A server.
        timeout:        Request + polling timeout in seconds.  Defaults to 30.

    Example::

        adapter = A2AClientAdapter("https://other-agent.example.com/.well-known/agent-card.json")
        result = await adapter.execute(task_envelope)
    """

    def __init__(
        self,
        agent_card_url: str,
        auth_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._agent_card_url = agent_card_url
        self._auth_token = auth_token
        self._timeout = timeout
        self._cached_card: dict[str, Any] | None = None
        self._rpc_endpoint: str | None = None  # resolved after first card fetch

    # ------------------------------------------------------------------
    # Adapter ABC
    # ------------------------------------------------------------------

    async def execute(self, task: TaskEnvelope) -> dict[str, Any]:
        """Delegate *task* to the remote A2A agent and return the result.

        Translates the :class:`~agentpassport.types.TaskEnvelope` to an A2A
        ``message/send`` request, sends it, then polls until completion.

        Args:
            task: The agentpassport task to execute remotely.

        Returns:
            A dict containing the result from the remote agent.  The structure
            depends on the remote agent's response; at minimum the key
            ``"a2a_task_id"`` will be present.

        Raises:
            TimeoutError: If the task does not reach a terminal state within
                ``self.timeout`` seconds.
            RuntimeError: If the remote agent returns a JSON-RPC error or the
                task fails.
        """
        card = await self._get_agent_card()
        endpoint = self._resolve_rpc_endpoint(card)

        headers = self._build_headers(task.auth_chain)
        request_body = self._build_jsonrpc_request(task)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                endpoint,
                json=request_body,
                headers=headers,
            )

        response.raise_for_status()
        rpc_response: dict[str, Any] = response.json()

        if "error" in rpc_response:
            err = rpc_response["error"]
            raise RuntimeError(
                f"A2A remote agent returned error {err.get('code')}: {err.get('message')}"
            )

        result = rpc_response.get("result", {})
        a2a_task: dict[str, Any] = result.get("task") or result

        # Check if we need to poll
        a2a_task = await self._poll_to_completion(a2a_task, endpoint, headers)

        return self._extract_result(a2a_task)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_agent_card(self) -> dict[str, Any]:
        """Fetch and cache the remote A2A agent's AgentCard.

        Returns:
            The AgentCard as a plain dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
            RuntimeError: On invalid JSON or missing card fields.
        """
        if self._cached_card is not None:
            return self._cached_card

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self._agent_card_url)

        resp.raise_for_status()
        try:
            card: dict[str, Any] = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Remote A2A agent at {self._agent_card_url!r} returned "
                f"non-JSON agent card: {exc}"
            ) from exc

        if "name" not in card:
            raise RuntimeError(
                f"Remote A2A agent card from {self._agent_card_url!r} is missing "
                "required field 'name'."
            )

        self._cached_card = card
        return card

    def _resolve_rpc_endpoint(self, card: dict[str, Any]) -> str:
        """Determine the JSON-RPC endpoint URL from an A2A AgentCard.

        Prefers the first ``supportedInterfaces`` URL.  Falls back to the
        base URL of the agent card path.

        Args:
            card: The AgentCard dict.

        Returns:
            The full URL to POST JSON-RPC requests to.

        Raises:
            RuntimeError: If no usable endpoint can be determined.
        """
        if self._rpc_endpoint:
            return self._rpc_endpoint

        interfaces: list[dict[str, Any]] = card.get("supportedInterfaces", [])
        if interfaces:
            url = interfaces[0].get("url", "")
            if url:
                self._rpc_endpoint = url
                return url

        # Derive from the agent card URL itself (strip path)
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(self._agent_card_url)
        base = urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))
        self._rpc_endpoint = base
        return base

    def _build_headers(self, auth_chain: list[str]) -> dict[str, str]:
        """Build HTTP headers for the A2A request.

        Adds ``Authorization`` if an auth token is configured, and
        ``X-AgentPassport-Auth-Chain`` when the task carries a chain.

        Args:
            auth_chain: The agentpassport delegation JWT chain.

        Returns:
            A dict of HTTP headers.
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        if auth_chain:
            headers[_AUTH_CHAIN_HEADER] = ", ".join(auth_chain)
        return headers

    def _build_jsonrpc_request(self, task: TaskEnvelope) -> dict[str, Any]:
        """Translate a :class:`TaskEnvelope` into an A2A JSON-RPC 2.0 payload.

        The A2A ``message/send`` method receives a ``SendMessageRequest`` whose
        ``message`` is populated from:

        * ``task.intent.params.get("text")`` → first text Part
        * ``task.intent.type`` → ``skillId`` metadata field
        * All other params → metadata

        Args:
            task: The agentpassport task to translate.

        Returns:
            A dict ready for ``json.dumps`` / httpx ``json=`` kwarg.
        """
        text_content: str = str(task.intent.params.get("text", ""))
        extra_params = {k: v for k, v in task.intent.params.items() if k != "text"}

        metadata: dict[str, Any] = {"skillId": task.intent.type, **extra_params}

        message: dict[str, Any] = {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_USER",
            "parts": [{"text": text_content}] if text_content else [],
            "metadata": metadata,
        }

        return {
            "jsonrpc": "2.0",
            "id": str(task.id),
            "method": "message/send",
            "params": {"message": message},
        }

    async def _poll_to_completion(
        self,
        initial_task: dict[str, Any],
        endpoint: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Poll the remote agent until the task reaches a terminal state.

        Many A2A agents return ``TASK_STATE_SUBMITTED`` or
        ``TASK_STATE_WORKING`` on the initial response.  This method polls
        ``tasks/get`` until the task is complete or the timeout expires.

        Args:
            initial_task: The A2A Task dict from the initial response.
            endpoint:     The agent's RPC endpoint URL.
            headers:      HTTP headers to include in poll requests.

        Returns:
            The final A2A Task dict in a terminal state.

        Raises:
            TimeoutError: If the task does not complete within ``self.timeout``.
            RuntimeError: If the task transitions to a failed state.
        """
        import asyncio
        import time

        task = initial_task
        deadline = time.monotonic() + self._timeout
        poll_interval = 0.5  # seconds

        while True:
            state = _get_task_state(task)
            if state in _TERMINAL_STATES:
                return task

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"A2A task '{task.get('id')}' did not complete within "
                    f"{self._timeout}s.  Last state: {state!r}"
                )

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 5.0)  # back off gently

            task_id = task.get("id", "")
            if not task_id:
                # Cannot poll without a task id — return as-is
                return task

            poll_body = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tasks/get",
                "params": {"id": task_id},
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                try:
                    resp = await client.post(endpoint, json=poll_body, headers=headers)
                    resp.raise_for_status()
                    rpc_resp: dict[str, Any] = resp.json()
                    if "result" in rpc_resp:
                        task = rpc_resp["result"].get("task", rpc_resp["result"])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Poll request failed (will retry): %s", exc)

    def _extract_result(self, a2a_task: dict[str, Any]) -> dict[str, Any]:
        """Extract a usable result dict from a completed A2A Task.

        Attempts to parse the status message text as JSON; falls back to a
        plain dict with the raw text.

        Args:
            a2a_task: A terminal A2A Task dict.

        Returns:
            A dict with at least ``"a2a_task_id"`` and the agent's output.

        Raises:
            RuntimeError: If the task state is ``TASK_STATE_FAILED``.
        """
        state = _get_task_state(a2a_task)

        if state == "TASK_STATE_FAILED":
            status = a2a_task.get("status", {})
            msg = status.get("message", {})
            err_text = _extract_text_from_a2a_message(msg) or "unknown failure"
            raise RuntimeError(
                f"Remote A2A task '{a2a_task.get('id')}' failed: {err_text}"
            )

        status = a2a_task.get("status", {})
        result_msg = status.get("message", {})
        raw_text = _extract_text_from_a2a_message(result_msg)

        result: dict[str, Any] = {"a2a_task_id": a2a_task.get("id")}

        if raw_text:
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, dict):
                    result.update(parsed)
                else:
                    result["result"] = parsed
            except json.JSONDecodeError:
                result["result"] = raw_text

        return result


# ---------------------------------------------------------------------------
# Small internal utilities
# ---------------------------------------------------------------------------


def _get_task_state(task: dict[str, Any]) -> str:
    """Extract the task state string from an A2A Task dict.

    Args:
        task: An A2A Task as a plain dict.

    Returns:
        The state string (e.g. ``"TASK_STATE_COMPLETED"``), or
        ``"TASK_STATE_UNSPECIFIED"`` if not present.
    """
    return task.get("status", {}).get("state", "TASK_STATE_UNSPECIFIED")


def _jsonrpc_error(
    rpc_id: Any,
    code: int,
    message: str,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response dict.

    Args:
        rpc_id:  The JSON-RPC request id (may be ``None``).
        code:    The error code.
        message: A human-readable error message.

    Returns:
        A dict conforming to the JSON-RPC 2.0 error response schema.
    """
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }
