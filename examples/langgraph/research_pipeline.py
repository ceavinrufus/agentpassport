"""LangGraph research pipeline with a signed delegation chain.

Orchestrator grants ``read:web`` to a researcher, who re-delegates that same
scope to a writer. The writer is a tool-calling node. Its model is a stub:
no API key and no network call. ``search_web`` is allowed. ``save_article``
needs ``write:db`` and is rejected before its handler runs.
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, TypedDict

from agentpassport import (
    Agent,
    EventEmitter,
    Intent,
    ScopeError,
    TaskEnvelope,
    generate_keypair,
    sign_delegation,
    verify_auth_chain,
)
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import START, StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition

# Tracing is opt-in for this example even if the surrounding shell has keys set.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

# The script runs the graph twice (invoke, then ainvoke). Only the first trace is printed.
_show_trace = True


def _log(message: str) -> None:
    if _show_trace:
        print(message)

_QUIET = EventEmitter(sinks=[])
_ORCH_PRIVATE, _ = generate_keypair()
_RESEARCHER_PRIVATE, _ = generate_keypair()

orchestrator = Agent("orchestrator", private_key=_ORCH_PRIVATE, emitter=_QUIET)
researcher = Agent("researcher", private_key=_RESEARCHER_PRIVATE, emitter=_QUIET)
writer = Agent("writer", emitter=_QUIET)

researcher.trust_keys({orchestrator.did: orchestrator.public_key})
writer.trust_keys(
    {
        orchestrator.did: orchestrator.public_key,
        researcher.did: researcher.public_key,
    }
)

_handlers_ran: list[str] = []


@writer.capability("search_web", requires=["read:web"])
async def _search_web(task: TaskEnvelope) -> dict[str, list[str]]:
    _handlers_ran.append("search_web")
    topic = str(task.intent.params.get("topic", ""))
    return {"snippets": [f"stub notes about {topic}"]}


@writer.capability("save_article", requires=["write:db"])
async def _save_article(_task: TaskEnvelope) -> dict[str, bool]:
    _handlers_ran.append("save_article")
    return {"stored": True}


def _writer_keys() -> dict[str, bytes]:
    return {
        orchestrator.did: orchestrator.public_key,
        researcher.did: researcher.public_key,
    }


async def _run_capability(
    name: str,
    params: dict[str, str],
    auth_chain: list[str],
) -> dict[str, object]:
    """Run the capability on the writer.

    ``handle`` checks the final subject, hop continuity, scope narrowing,
    and the capability's required scope. It does not consult a revocation
    registry.
    """
    task = TaskEnvelope(
        intent=Intent(type=name, params=params),
        auth_chain=list(auth_chain),
    )
    return await writer.handle(task)


def _scope_denied(exc: ScopeError) -> str:
    return f"SCOPE_DENIED: {exc}"


async def _search_web(
    topic: str,
    auth_chain: Annotated[list[str], InjectedState("auth_chain")],
) -> str:
    """Look up sources for a topic. Requires the read:web scope."""
    try:
        result = await _run_capability("search_web", {"topic": topic}, auth_chain)
    except ScopeError as exc:
        return _scope_denied(exc)
    snippets = result["snippets"]
    if not isinstance(snippets, list):
        raise TypeError("search_web did not return snippets")
    return "\n".join(str(item) for item in snippets)


def _search_web_sync(
    topic: str,
    auth_chain: Annotated[list[str], InjectedState("auth_chain")],
) -> str:
    """Look up sources for a topic. Requires the read:web scope."""
    # invoke() has no running loop. ainvoke() calls _search_web directly.
    return asyncio.run(_search_web(topic, auth_chain))


async def _save_article_tool(
    body: str,
    auth_chain: Annotated[list[str], InjectedState("auth_chain")],
) -> str:
    """Persist an article. Requires the write:db scope."""
    try:
        await _run_capability("save_article", {"body": body}, auth_chain)
    except ScopeError as exc:
        return _scope_denied(exc)
    return "stored"


def _save_article_sync(
    body: str,
    auth_chain: Annotated[list[str], InjectedState("auth_chain")],
) -> str:
    """Persist an article. Requires the write:db scope."""
    return asyncio.run(_save_article_tool(body, auth_chain))


# Both entry points: ainvoke awaits the coroutine and does not call asyncio.run.
search_web = StructuredTool.from_function(
    func=_search_web_sync,
    coroutine=_search_web,
    name="search_web",
)
save_article = StructuredTool.from_function(
    func=_save_article_sync,
    coroutine=_save_article_tool,
    name="save_article",
)


class ResearchState(TypedDict):
    topic: str
    notes: str
    auth_chain: list[str]
    messages: Annotated[list[BaseMessage], add_messages]
    article: str
    search_result: str
    save_result: str


def orchestrator_node(_state: ResearchState) -> dict[str, list[str]]:
    """Root grant. The researcher may read the web and delegate once."""
    token = sign_delegation(
        issuer_private_key=_ORCH_PRIVATE,
        issuer_did=orchestrator.did,
        subject_did=researcher.did,
        scope=["read:web"],
        ttl_seconds=3600,
        max_delegations=1,
    )
    _log("[orchestrator] signed delegation -> researcher | scope: read:web")
    return {"auth_chain": [token]}


def researcher_node(state: ResearchState) -> dict[str, str | list[str]]:
    """Verify the grant, then re-delegate the same scope to the writer."""
    chain_ok = verify_auth_chain(
        auth_chain=state["auth_chain"],
        expected_subject=researcher.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
    )
    if not chain_ok:
        raise RuntimeError("researcher rejected the delegation chain")

    # sign_delegation will sign write:db if asked; it does not read the parent
    # grant. This hop passes read:web only. writer.handle and verify_auth_chain
    # both reject a widened hop — see _assert_over_grant_denied.
    token = sign_delegation(
        issuer_private_key=_RESEARCHER_PRIVATE,
        issuer_did=researcher.did,
        subject_did=writer.did,
        scope=["read:web"],
        ttl_seconds=1800,
        max_delegations=0,
    )
    _log("[researcher] chain verified | delegated -> writer | scope: read:web")
    return {
        "notes": f"Research notes on {state['topic']}.",
        "auth_chain": [*state["auth_chain"], token],
    }


def _tool_text(messages: list[BaseMessage], name: str) -> str:
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == name:
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise RuntimeError(f"missing tool result for {name}")


def writer_node(state: ResearchState) -> dict[str, object]:
    """Stub model. Replace this with a chat model bound to the same tools.

    First turn calls both tools. Second turn writes the article and stops,
    which routes the graph to the end.
    """
    tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]
    if not tool_messages:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_web",
                            "args": {"topic": state["topic"]},
                            "id": "call_search",
                            "type": "tool_call",
                        },
                        {
                            "name": "save_article",
                            "args": {"body": state["notes"]},
                            "id": "call_save",
                            "type": "tool_call",
                        },
                    ],
                )
            ]
        }

    search = _tool_text(state["messages"], "search_web")
    save = _tool_text(state["messages"], "save_article")
    article = f"# {state['topic']}\n\n{state['notes']}\n\n{search}\n"
    _log(f"[writer] search_web -> {search}")
    _log(f"[writer] save_article -> {save}")
    return {
        "messages": [AIMessage(content=article)],
        "article": article,
        "search_result": search,
        "save_result": save,
    }


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(ResearchState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("writer", writer_node)
    graph.add_node("tools", ToolNode([search_web, save_article]))
    graph.add_edge(START, "orchestrator")
    graph.add_edge("orchestrator", "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_conditional_edges("writer", tools_condition)
    graph.add_edge("tools", "writer")
    return graph.compile()


def _initial_state(topic: str) -> ResearchState:
    return {
        "topic": topic,
        "notes": "",
        "auth_chain": [],
        "messages": [],
        "article": "",
        "search_result": "",
        "save_result": "",
    }


def _over_granted_chain() -> list[str]:
    """Researcher adds write:db, which the root grant does not contain."""
    root = sign_delegation(
        issuer_private_key=_ORCH_PRIVATE,
        issuer_did=orchestrator.did,
        subject_did=researcher.did,
        scope=["read:web"],
        ttl_seconds=3600,
        max_delegations=1,
    )
    widened = sign_delegation(
        issuer_private_key=_RESEARCHER_PRIVATE,
        issuer_did=researcher.did,
        subject_did=writer.did,
        scope=["read:web", "write:db"],
        ttl_seconds=1800,
        max_delegations=0,
    )
    return [root, widened]


def _assert_happy_path(result: ResearchState, topic: str) -> None:
    chain_ok = verify_auth_chain(
        auth_chain=result["auth_chain"],
        expected_subject=writer.did,
        known_public_keys=_writer_keys(),
    )
    search = str(result["search_result"])
    save = str(result["save_result"])
    if not chain_ok or len(result["auth_chain"]) != 2:
        raise SystemExit("delegation chain did not verify for the writer")
    if not result["notes"]:
        raise SystemExit("researcher did not record notes")
    if "search_web" not in _handlers_ran or topic not in search:
        raise SystemExit(f"search_web did not run under read:web: {search!r}")
    if "save_article" in _handlers_ran:
        raise SystemExit("save_article handler ran without write:db")
    if "SCOPE_DENIED" not in save or "write:db" not in save:
        raise SystemExit(f"expected save_article to be denied for write:db, got {save!r}")


async def _assert_over_grant_denied() -> None:
    """A widened hop fails verify_auth_chain, and handle denies the tool."""
    chain = _over_granted_chain()
    if verify_auth_chain(
        auth_chain=chain,
        expected_subject=writer.did,
        known_public_keys=_writer_keys(),
    ):
        raise SystemExit("over-grant of write:db should fail verify_auth_chain")

    ran_before = len(_handlers_ran)
    try:
        await _run_capability("save_article", {"body": "draft"}, chain)
    except ScopeError:
        pass
    else:
        raise SystemExit("tool path accepted a chain that failed verification")
    if len(_handlers_ran) != ran_before:
        raise SystemExit("save_article handler ran after verify_auth_chain failed")

    try:
        await writer.handle(
            TaskEnvelope(
                intent=Intent(type="save_article", params={"body": "draft"}),
                auth_chain=chain,
            )
        )
    except ScopeError as exc:
        if "write:db" not in str(exc):
            raise SystemExit(f"handle denied without mentioning write:db: {exc}") from exc
    else:
        raise SystemExit("writer.handle should deny write:db on an over-granted chain")
    if "save_article" in _handlers_ran:
        raise SystemExit("save_article handler ran on an over-granted chain")

    print("[researcher] over-granted write:db: verify_auth_chain is false")
    print("[writer] save_article denied on that chain")


def main() -> None:
    global _show_trace

    topic = "cryptographic delegation in multi-agent systems"
    graph = build_graph()
    result = graph.invoke(_initial_state(topic))
    _assert_happy_path(result, topic)
    print(f"auth chain hops: {len(result['auth_chain'])}")
    print(str(result["article"]).rstrip())

    # Same tools under ainvoke. They await handle; they do not call asyncio.run.
    _show_trace = False
    again = asyncio.run(graph.ainvoke(_initial_state(topic)))
    _assert_happy_path(again, topic)
    asyncio.run(_assert_over_grant_denied())
    print("example ok")


if __name__ == "__main__":
    main()
