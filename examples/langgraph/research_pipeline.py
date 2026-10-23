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
from langchain_core.tools import tool
from langgraph.graph import START, StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition

# Tracing is opt-in for this example even if the surrounding shell has keys set.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

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


def _run_capability(name: str, params: dict[str, str], auth_chain: list[str]) -> dict[str, object]:
    """Dispatch a tool through the writer agent so scope is checked first.

    ``graph.invoke`` is synchronous, so each tool call opens its own event loop.
    """
    task = TaskEnvelope(
        intent=Intent(type=name, params=params),
        auth_chain=list(auth_chain),
    )
    return asyncio.run(writer.handle(task))


@tool
def search_web(
    topic: str,
    auth_chain: Annotated[list[str], InjectedState("auth_chain")],
) -> str:
    """Look up sources for a topic. Requires the read:web scope."""
    try:
        result = _run_capability("search_web", {"topic": topic}, auth_chain)
    except ScopeError as exc:
        return f"SCOPE_DENIED: {exc}"
    snippets = result["snippets"]
    if not isinstance(snippets, list):
        raise TypeError("search_web did not return snippets")
    return "\n".join(str(item) for item in snippets)


@tool
def save_article(
    body: str,
    auth_chain: Annotated[list[str], InjectedState("auth_chain")],
) -> str:
    """Persist an article. Requires the write:db scope."""
    try:
        _run_capability("save_article", {"body": body}, auth_chain)
    except ScopeError as exc:
        return f"SCOPE_DENIED: {exc}"
    return "stored"


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
    print("[orchestrator] signed delegation -> researcher | scope: read:web")
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

    # read:web is the only scope this hop holds, so it cannot grant write:db.
    token = sign_delegation(
        issuer_private_key=_RESEARCHER_PRIVATE,
        issuer_did=researcher.did,
        subject_did=writer.did,
        scope=["read:web"],
        ttl_seconds=1800,
        max_delegations=0,
    )
    print("[researcher] chain verified | delegated -> writer | scope: read:web")
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
    print(f"[writer] search_web -> {search}")
    print(f"[writer] save_article -> {save}")
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


def main() -> None:
    topic = "cryptographic delegation in multi-agent systems"
    result = build_graph().invoke(_initial_state(topic))

    chain_ok = verify_auth_chain(
        auth_chain=result["auth_chain"],
        expected_subject=writer.did,
        known_public_keys={
            orchestrator.did: orchestrator.public_key,
            researcher.did: researcher.public_key,
        },
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

    print(f"auth chain hops: {len(result['auth_chain'])}")
    print(str(result["article"]).rstrip())
    print("example ok")


if __name__ == "__main__":
    main()
