"""Tests for the A2A adapter (agentpassport-adapters).

Coverage:
- synthesize_a2a_agent_card: all fields mapped correctly
- A2AServerAdapter: happy path, ScopeError, missing auth chain on protected
  capability, unknown skill, parse error, multi-capability without skillId
- A2AClientAdapter: successful delegation, timeout, failed A2A task, card fetch
  error, cached card, auth chain injection
- Agent.card property
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agentpassport.agent import Agent
from agentpassport.trust import ScopeError
from agentpassport.types import AgentCard as APSAgentCard, Intent, TaskEnvelope
from agentpassport_adapters.a2a import (
    A2AClientAdapter,
    A2AServerAdapter,
    _build_a2a_task,
    _extract_text_from_a2a_message,
    _get_task_state,
    _jsonrpc_error,
    synthesize_a2a_agent_card,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_aps_card(
    did: str = "did:key:z6MkTest",
    name: str = "TestAgent",
    capabilities: list[str] | None = None,
    endpoint: str = "http://localhost:8000",
    signature: str | None = "abc123",
) -> APSAgentCard:
    return APSAgentCard(
        did=did,
        name=name,
        capabilities=capabilities or ["search", "summarize"],
        endpoint=endpoint,
        signature=signature,
    )


def make_agent(name: str = "TestAgent") -> Agent:
    return Agent(name=name)


def make_task(
    capability: str = "search",
    params: dict[str, Any] | None = None,
    auth_chain: list[str] | None = None,
) -> TaskEnvelope:
    return TaskEnvelope(
        intent=Intent(type=capability, params=params or {"text": "hello"}),
        auth_chain=auth_chain or [],
    )


def make_jsonrpc_request(
    method: str = "message/send",
    skill_id: str = "search",
    text: str = "hello",
    rpc_id: str = "req-1",
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": text}],
                "metadata": {"skillId": skill_id},
            }
        },
    }


# ---------------------------------------------------------------------------
# synthesize_a2a_agent_card
# ---------------------------------------------------------------------------


class TestSynthesizeA2aAgentCard:
    def test_name_and_description(self) -> None:
        card = make_aps_card(name="MyBot")
        result = synthesize_a2a_agent_card(card)
        assert result["name"] == "MyBot"

    def test_skills_from_capabilities(self) -> None:
        card = make_aps_card(capabilities=["search", "summarize"])
        result = synthesize_a2a_agent_card(card)
        skill_ids = {s["id"] for s in result["skills"]}
        skill_names = {s["name"] for s in result["skills"]}
        assert skill_ids == {"search", "summarize"}
        assert skill_names == {"search", "summarize"}

    def test_supported_interfaces_from_endpoint(self) -> None:
        card = make_aps_card(endpoint="http://agent.example.com/")
        result = synthesize_a2a_agent_card(card)
        urls = [iface["url"] for iface in result.get("supportedInterfaces", [])]
        assert "http://agent.example.com/" in urls

    def test_endpoint_override(self) -> None:
        card = make_aps_card(endpoint="http://old.example.com/")
        result = synthesize_a2a_agent_card(card, endpoint="http://new.example.com/")
        urls = [iface["url"] for iface in result.get("supportedInterfaces", [])]
        assert "http://new.example.com/" in urls
        assert "http://old.example.com/" not in urls

    def test_did_extension_field(self) -> None:
        card = make_aps_card(did="did:key:z6Mkfoo")
        result = synthesize_a2a_agent_card(card)
        assert result["x_agentpassport_did"] == "did:key:z6Mkfoo"

    def test_signature_extension_field(self) -> None:
        card = make_aps_card(signature="deadbeef")
        result = synthesize_a2a_agent_card(card)
        assert result["x_agentpassport_signature"] == "deadbeef"

    def test_no_signature_omits_field(self) -> None:
        card = make_aps_card(signature=None)
        result = synthesize_a2a_agent_card(card)
        assert "x_agentpassport_signature" not in result

    def test_empty_capabilities(self) -> None:
        card = APSAgentCard(
            did="did:key:z6MkX",
            name="Empty",
            capabilities=[],
            endpoint="http://x.example.com",
        )
        result = synthesize_a2a_agent_card(card)
        # When capabilities are empty, skills should be absent or an empty list
        assert result.get("skills", []) == []

    def test_no_endpoint_produces_no_interfaces(self) -> None:
        card = APSAgentCard(
            did="did:key:z6MkX",
            name="Minimal",
            capabilities=["foo"],
            endpoint="",
        )
        result = synthesize_a2a_agent_card(card)
        interfaces = result.get("supportedInterfaces", [])
        assert interfaces == []


# ---------------------------------------------------------------------------
# Agent.card property
# ---------------------------------------------------------------------------


class TestAgentCardProperty:
    def test_card_returns_agent_card(self) -> None:
        agent = make_agent(name="Hal")
        card = agent.card
        assert isinstance(card, APSAgentCard)

    def test_card_did_matches_agent_did(self) -> None:
        agent = make_agent()
        assert agent.card.did == agent.did

    def test_card_name_matches_agent_name(self) -> None:
        agent = make_agent(name="Dave")
        assert agent.card.name == "Dave"

    def test_card_capabilities_reflect_registered(self) -> None:
        agent = make_agent()

        @agent.capability("search")
        async def _search(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        @agent.capability("summarize")
        async def _summarize(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        assert set(agent.card.capabilities) == {"search", "summarize"}

    def test_card_endpoint_is_empty(self) -> None:
        agent = make_agent()
        assert agent.card.endpoint == ""

    def test_card_no_capabilities_empty_list(self) -> None:
        agent = make_agent()
        assert agent.card.capabilities == []


# ---------------------------------------------------------------------------
# Helpers: _extract_text_from_a2a_message, _get_task_state, etc.
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_extract_text_single_part(self) -> None:
        msg = {"parts": [{"text": "hello"}]}
        assert _extract_text_from_a2a_message(msg) == "hello"

    def test_extract_text_multiple_parts(self) -> None:
        msg = {"parts": [{"text": "foo"}, {"text": "bar"}]}
        assert _extract_text_from_a2a_message(msg) == "foo\nbar"

    def test_extract_text_non_text_parts(self) -> None:
        msg = {"parts": [{"url": "http://example.com"}, {"text": "hi"}]}
        assert _extract_text_from_a2a_message(msg) == "hi"

    def test_extract_text_empty_parts(self) -> None:
        assert _extract_text_from_a2a_message({}) == ""

    def test_get_task_state_present(self) -> None:
        task = {"status": {"state": "TASK_STATE_COMPLETED"}}
        assert _get_task_state(task) == "TASK_STATE_COMPLETED"

    def test_get_task_state_missing(self) -> None:
        assert _get_task_state({}) == "TASK_STATE_UNSPECIFIED"

    def test_jsonrpc_error_structure(self) -> None:
        err = _jsonrpc_error("req-1", -32601, "not found")
        assert err["jsonrpc"] == "2.0"
        assert err["id"] == "req-1"
        assert err["error"]["code"] == -32601
        assert err["error"]["message"] == "not found"

    def test_build_a2a_task_completed(self) -> None:
        task = _build_a2a_task("task-1", "TASK_STATE_COMPLETED", "done")
        assert task["id"] == "task-1"
        state = task.get("status", {}).get("state", "")
        assert "COMPLETED" in state

    def test_build_a2a_task_failed(self) -> None:
        task = _build_a2a_task("task-2", "TASK_STATE_FAILED", "oops")
        assert task["id"] == "task-2"


# ---------------------------------------------------------------------------
# A2AServerAdapter — Starlette app tests (via TestClient)
# ---------------------------------------------------------------------------


def _make_server_adapter(
    agent: Agent | None = None,
    card: APSAgentCard | None = None,
    endpoint: str = "http://localhost:8080",
    skill_map: dict[str, str] | None = None,
) -> A2AServerAdapter:
    if agent is None:
        agent = make_agent()
    return A2AServerAdapter(
        agent=agent,
        agent_card=card or make_aps_card(),
        endpoint=endpoint,
        skill_map=skill_map,
    )


class TestA2AServerAdapterAgentCard:
    def test_agent_card_endpoint_returns_200(self) -> None:
        from starlette.testclient import TestClient

        adapter = _make_server_adapter()
        app = adapter.build_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200

    def test_agent_card_contains_name(self) -> None:
        from starlette.testclient import TestClient

        card = make_aps_card(name="Orion")
        adapter = _make_server_adapter(card=card)
        app = adapter.build_app()
        with TestClient(app) as client:
            data = client.get("/.well-known/agent-card.json").json()
        assert data["name"] == "Orion"

    def test_agent_card_fallback_to_agent_card_property(self) -> None:
        """When no card is passed, agent.card should be used."""
        from starlette.testclient import TestClient

        agent = make_agent(name="FallbackAgent")

        @agent.capability("ping")
        async def _ping(task: TaskEnvelope) -> dict[str, Any]:
            return {"pong": True}

        adapter = A2AServerAdapter(agent=agent, endpoint="http://localhost:9000")
        app = adapter.build_app()
        with TestClient(app) as client:
            data = client.get("/.well-known/agent-card.json").json()
        assert data["name"] == "FallbackAgent"


class TestA2AServerAdapterHappyPath:
    def test_message_send_returns_completed_task(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("search")
        async def _search(task: TaskEnvelope) -> dict[str, Any]:
            return {"results": ["r1", "r2"]}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        with TestClient(app) as client:
            resp = client.post("/", json=make_jsonrpc_request(skill_id="search"))

        assert resp.status_code == 200
        body = resp.json()
        assert "result" in body
        a2a_task = body["result"]["task"]
        state = a2a_task["status"]["state"]
        assert "COMPLETED" in state

    def test_result_text_contains_handler_output(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("echo")
        async def _echo(task: TaskEnvelope) -> dict[str, Any]:
            return {"echoed": task.intent.params.get("text")}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        with TestClient(app) as client:
            resp = client.post(
                "/", json=make_jsonrpc_request(skill_id="echo", text="ping")
            )

        body = resp.json()
        task_text = body["result"]["task"]["status"]["message"]["parts"][0]["text"]
        data = json.loads(task_text)
        assert data["echoed"] == "ping"

    def test_skill_map_applied(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("internal_search")
        async def _search(task: TaskEnvelope) -> dict[str, Any]:
            return {"ok": True}

        adapter = _make_server_adapter(
            agent=agent,
            skill_map={"public-search": "internal_search"},
        )
        app = adapter.build_app()

        with TestClient(app) as client:
            resp = client.post(
                "/", json=make_jsonrpc_request(skill_id="public-search")
            )

        assert resp.status_code == 200
        assert "result" in resp.json()

    def test_single_capability_no_skill_id_dispatches(self) -> None:
        """When there is exactly one capability, missing skillId should still work."""
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("only_one")
        async def _handler(task: TaskEnvelope) -> dict[str, Any]:
            return {"ok": True}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        body = {
            "jsonrpc": "2.0",
            "id": "r1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"text": "hi"}],
                    "metadata": {},
                }
            },
        }
        with TestClient(app) as client:
            resp = client.post("/", json=body)

        assert resp.status_code == 200
        assert "result" in resp.json()


class TestA2AServerAdapterErrors:
    def test_unknown_skill_returns_error(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("search")
        async def _search(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/", json=make_jsonrpc_request(skill_id="nonexistent"))

        body = resp.json()
        assert "error" in body
        assert "nonexistent" in body["error"]["message"]

    def test_scope_error_returns_jsonrpc_error_not_500(self) -> None:
        """ScopeError must not turn into a 500."""
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("secret", requires=["admin:read"])
        async def _secret(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        # no auth chain header → ScopeError
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/", json=make_jsonrpc_request(skill_id="secret"))

        assert resp.status_code == 200  # JSON-RPC always 200
        body = resp.json()
        assert "error" in body
        assert "Authorization denied" in body["error"]["message"]

    def test_missing_auth_chain_on_protected_capability(self) -> None:
        """Protected capability without X-AgentPassport-Auth-Chain must error."""
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("restricted", requires=["read:secret"])
        async def _restricted(task: TaskEnvelope) -> dict[str, Any]:
            return {"data": "sensitive"}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        req = make_jsonrpc_request(skill_id="restricted")
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/", json=req)

        body = resp.json()
        assert "error" in body

    def test_method_not_found(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("search")
        async def _search(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        req = make_jsonrpc_request(method="tasks/get")
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/", json=req)

        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32601

    def test_invalid_json_body(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("search")
        async def _search(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/",
                content=b"not json",
                headers={"Content-Type": "application/json"},
            )

        body = resp.json()
        assert "error" in body

    def test_multiple_capabilities_without_skill_id_returns_error(self) -> None:
        from starlette.testclient import TestClient

        agent = make_agent()

        @agent.capability("cap_a")
        async def _a(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        @agent.capability("cap_b")
        async def _b(task: TaskEnvelope) -> dict[str, Any]:
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        body = {
            "jsonrpc": "2.0",
            "id": "r1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"text": "hi"}],
                    "metadata": {},
                }
            },
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/", json=body)

        body_resp = resp.json()
        assert "error" in body_resp


class TestA2AServerAdapterAuthChain:
    def test_auth_chain_header_parsed_into_envelope(self) -> None:
        from starlette.testclient import TestClient

        captured: list[list[str]] = []
        agent = make_agent()

        @agent.capability("inspect")
        async def _inspect(task: TaskEnvelope) -> dict[str, Any]:
            captured.append(list(task.auth_chain))
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        with TestClient(app) as client:
            resp = client.post(
                "/",
                json=make_jsonrpc_request(skill_id="inspect"),
                headers={"X-AgentPassport-Auth-Chain": "jwt1, jwt2"},
            )

        assert resp.status_code == 200
        assert captured == [["jwt1", "jwt2"]]

    def test_no_auth_chain_header_gives_empty_chain(self) -> None:
        from starlette.testclient import TestClient

        captured: list[list[str]] = []
        agent = make_agent()

        @agent.capability("inspect")
        async def _inspect(task: TaskEnvelope) -> dict[str, Any]:
            captured.append(list(task.auth_chain))
            return {}

        adapter = _make_server_adapter(agent=agent)
        app = adapter.build_app()

        with TestClient(app) as client:
            client.post("/", json=make_jsonrpc_request(skill_id="inspect"))

        assert captured == [[]]


# ---------------------------------------------------------------------------
# A2AClientAdapter
# ---------------------------------------------------------------------------


def _make_a2a_task_response(
    task_id: str = "task-abc",
    state: str = "TASK_STATE_COMPLETED",
    result_text: str = '{"answer": 42}',
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": "r1",
        "result": {
            "task": {
                "id": task_id,
                "status": {
                    "state": state,
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_AGENT",
                        "parts": [{"text": result_text}],
                    },
                },
            }
        },
    }


def _make_mock_transport(responses: list[httpx.Response]) -> Any:
    """Build an httpx MockTransport that returns *responses* in order."""
    calls: list[int] = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        idx = calls[0]
        calls[0] += 1
        if idx < len(responses):
            return responses[idx]
        return responses[-1]  # repeat last

    return httpx.MockTransport(handler)


def _json_resp(data: Any, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "http://test.example.com/")
    return httpx.Response(status_code, json=data, request=request)


SAMPLE_CARD = {
    "name": "RemoteAgent",
    "skills": [{"id": "answer", "name": "answer"}],
    "supportedInterfaces": [{"url": "http://remote-agent.example.com/"}],
}


class TestA2AClientAdapterHappyPath:
    async def test_successful_delegation_returns_result(self) -> None:
        transport = _make_mock_transport([
            _json_resp(SAMPLE_CARD),  # card fetch
            _json_resp(_make_a2a_task_response()),  # message/send
        ])

        adapter = A2AClientAdapter(
            agent_card_url="http://remote-agent.example.com/.well-known/agent-card.json",
            timeout=5.0,
        )

        with patch("httpx.AsyncClient") as mock_cls:
            # Set up context manager returning client with side_effect-based responses
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            call_count = [0]
            async def fake_get(url: str, **kwargs: Any) -> httpx.Response:
                return _json_resp(SAMPLE_CARD)

            async def fake_post(url: str, **kwargs: Any) -> httpx.Response:
                return _json_resp(_make_a2a_task_response(result_text='{"answer": 42}'))

            mock_client.get = fake_get
            mock_client.post = fake_post

            # Patch internally used AsyncClient instances
            task = make_task(capability="answer")
            result = await adapter.execute(task)

        assert result.get("answer") == 42

    async def test_auth_chain_injected_into_headers(self) -> None:
        received_headers: list[dict[str, str]] = []
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
        )
        adapter._cached_card = SAMPLE_CARD  # skip card fetch

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_post(url: str, *, json: Any, headers: dict[str, str], **kwargs: Any) -> httpx.Response:
                received_headers.append(dict(headers))
                return _json_resp(_make_a2a_task_response())

            mock_client.post = fake_post

            task = make_task(auth_chain=["jwt-a", "jwt-b"])
            await adapter.execute(task)

        assert received_headers[0].get("X-AgentPassport-Auth-Chain") == "jwt-a, jwt-b"

    async def test_auth_token_injected_as_bearer(self) -> None:
        received_headers: list[dict[str, str]] = []
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
            auth_token="mytoken",
        )
        adapter._cached_card = SAMPLE_CARD

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_post(url: str, *, json: Any, headers: dict[str, str], **kwargs: Any) -> httpx.Response:
                received_headers.append(dict(headers))
                return _json_resp(_make_a2a_task_response())

            mock_client.post = fake_post

            await adapter.execute(make_task())

        assert received_headers[0].get("Authorization") == "Bearer mytoken"

    async def test_card_is_cached(self) -> None:
        """Second execute() should not re-fetch the card."""
        fetch_count = [0]
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_get(url: str, **kwargs: Any) -> httpx.Response:
                fetch_count[0] += 1
                return _json_resp(SAMPLE_CARD)

            async def fake_post(url: str, **kwargs: Any) -> httpx.Response:
                return _json_resp(_make_a2a_task_response())

            mock_client.get = fake_get
            mock_client.post = fake_post

            await adapter.execute(make_task())
            await adapter.execute(make_task())

        assert fetch_count[0] == 1


class TestA2AClientAdapterErrors:
    async def test_failed_task_raises_runtime_error(self) -> None:
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
        )
        adapter._cached_card = SAMPLE_CARD

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_post(url: str, **kwargs: Any) -> httpx.Response:
                return _json_resp(
                    _make_a2a_task_response(state="TASK_STATE_FAILED", result_text="broken")
                )

            mock_client.post = fake_post

            with pytest.raises(RuntimeError, match="failed"):
                await adapter.execute(make_task())

    async def test_jsonrpc_error_raises_runtime_error(self) -> None:
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
        )
        adapter._cached_card = SAMPLE_CARD

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_post(url: str, **kwargs: Any) -> httpx.Response:
                return _json_resp({"jsonrpc": "2.0", "id": "r1", "error": {"code": -32000, "message": "Forbidden"}})

            mock_client.post = fake_post

            with pytest.raises(RuntimeError, match="Forbidden"):
                await adapter.execute(make_task())

    async def test_timeout_raises_timeout_error(self) -> None:
        """If polling never reaches terminal state, TimeoutError is raised."""
        import asyncio

        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
            timeout=0.1,  # very short
        )
        adapter._cached_card = SAMPLE_CARD

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_post(url: str, **kwargs: Any) -> httpx.Response:
                # Always return WORKING — never completes
                return _json_resp(
                    _make_a2a_task_response(state="TASK_STATE_WORKING", result_text="still going")
                )

            mock_client.post = fake_post

            with pytest.raises(TimeoutError, match="did not complete"):
                await adapter.execute(make_task())

    async def test_card_fetch_http_error_propagates(self) -> None:
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_get(url: str, **kwargs: Any) -> httpx.Response:
                request = httpx.Request("GET", url)
                return httpx.Response(404, request=request)

            mock_client.get = fake_get

            with pytest.raises(httpx.HTTPStatusError):
                await adapter.execute(make_task())

    async def test_card_missing_name_field_raises(self) -> None:
        adapter = A2AClientAdapter(
            agent_card_url="http://remote.example.com/.well-known/agent-card.json",
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_get(url: str, **kwargs: Any) -> httpx.Response:
                return _json_resp({"skills": []})  # missing 'name'

            mock_client.get = fake_get

            with pytest.raises(RuntimeError, match="missing required field 'name'"):
                await adapter.execute(make_task())

    async def test_rpc_endpoint_derived_from_card_url_when_no_interfaces(self) -> None:
        """Falls back to base URL of agent_card_url when no supportedInterfaces."""
        posted_urls: list[str] = []
        adapter = A2AClientAdapter(
            agent_card_url="http://fallback.example.com/.well-known/agent-card.json",
        )
        adapter._cached_card = {"name": "Agent", "skills": [], "supportedInterfaces": []}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def fake_post(url: str, **kwargs: Any) -> httpx.Response:
                posted_urls.append(url)
                return _json_resp(_make_a2a_task_response())

            mock_client.post = fake_post

            await adapter.execute(make_task())

        assert posted_urls[0].startswith("http://fallback.example.com")
