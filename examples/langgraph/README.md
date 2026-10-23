# LangGraph + agentpassport: Scoped delegation for multi-agent workflows

LangGraph gives you stateful graphs, conditional edges, human-in-the-loop checkpoints, and streaming. It does not authorize one node to call another.

When a researcher delegates to a writer, nothing in the graph says "this node may do X and only X." Trust flows by convention: if you are in the graph, you can do anything in the graph.

This example adds a signed delegation chain between LangGraph nodes with agentpassport. An orchestrator grants `read:web` to a researcher, who re-delegates that same scope to a writer. The writer can search. It cannot persist. The scope check runs before the capability handler.

The runnable script is [`research_pipeline.py`](research_pipeline.py). CI executes that file, so this page describes it instead of keeping a second copy of the program.

## What we're building

```
[Orchestrator] → delegates(scope=read:web) → [Researcher]
                                                    ↓
                                   delegates(scope=read:web) → [Writer]
                                                                   ↓
                              search_web (read:web)     → runs
                              save_article (write:db)   → ScopeError before the handler
```

The writer node is a tool-calling model. The model in this file is a stub: it always calls `search_web` and `save_article`, then stops. No API key and no network call. Replace `writer_node` with a chat model bound to the same tools when you want a live model.

## What the script checks

Delegation tokens are signed with `sign_delegation`. That function signs the scope you pass. It does not look at the parent grant, so a researcher can put `write:db` on a token even if it was only given `read:web`.

`writer.handle` rejects that expansion. It applies the same rules as `verify_auth_chain`: the final subject is the writer, each hop's issuer is the previous subject, and scope only narrows. It then checks the scope declared on the capability (`requires=["read:web"]` or `requires=["write:db"]`). It does not consult a revocation registry. On the happy path the chain is `read:web` only, so `search_web` runs and `save_article` raises `ScopeError` before its handler.

The researcher calls `verify_auth_chain` with `expected_subject=researcher.did` before re-delegating. That check is the researcher's own grant. The writer does not need a second copy of it.

The script also builds a negative chain where the researcher over-grants `write:db`. `verify_auth_chain` returns false for that chain, and `writer.handle` denies `save_article` for the same reason, without running the handler.

Tools register a sync function and a coroutine. `graph.invoke` uses the sync function. `graph.ainvoke` awaits the coroutine, so a tool call does not open a nested event loop with `asyncio.run`.

## Run

From the repository root, against the SDK in this checkout:

```bash
uv venv --python 3.12 /tmp/agentpassport-example-langgraph
uv pip install --python /tmp/agentpassport-example-langgraph/bin/python \
  -e packages/agentpassport \
  -r examples/langgraph/requirements.txt
/tmp/agentpassport-example-langgraph/bin/python examples/langgraph/research_pipeline.py
```

Outside this repo, install the published packages and run the same file:

```bash
pip install langgraph agentpassport
python research_pipeline.py
```

The script exits 0 only when the two-hop chain verifies, `search_web` returns notes, `save_article` is denied without running its handler, the same graph succeeds under `ainvoke`, and the over-granted chain is rejected.

Expected output:

```
[orchestrator] signed delegation -> researcher | scope: read:web
[researcher] chain verified | delegated -> writer | scope: read:web
[writer] search_web -> stub notes about cryptographic delegation in multi-agent systems
[writer] save_article -> SCOPE_DENIED: Capability 'save_article' requires scope ['write:db'] not granted by the auth chain. Granted: ['read:web']
auth chain hops: 2
# cryptographic delegation in multi-agent systems

Research notes on cryptographic delegation in multi-agent systems.

stub notes about cryptographic delegation in multi-agent systems
[researcher] over-granted write:db: verify_auth_chain is false
[writer] save_article denied on that chain
example ok
```

The writer can read. It cannot write to the database. The scope check happens before the handler runs.

## What this gives you

- **Auditable delegation chains.** Every hop is a signed JWT. You can trace who authorized what, when, and with what scope.
- **Fail-fast scope enforcement.** Capabilities declare what they need. agentpassport checks before the handler runs. A bad request does not leave partial work behind.
- **Narrowing.** A hop can pass on a subset of its scope. It cannot widen the chain. `verify_auth_chain` and `Agent.handle` both reject the widened token.
- **Revocation without process kills.** Revoke a delegation by JTI. The current action can finish; the next check fails. This script keeps the registry out of the path; see `InMemoryRevocationRegistry` and `SqliteRevocationRegistry`.
- **Cross-language.** A LangGraph orchestrator can delegate to a TypeScript agent and the same chain verifies. See `examples/typescript`.

## What's next

- Add `SqliteRevocationRegistry` for persistent revocation across restarts
- Point `writer_node` at a real chat model bound to `search_web` and `save_article`
- Use `agentpassport-adapters` for MCP or A2A protocol integration

---

**agentpassport** — The authorization layer for multi-agent AI systems.

GitHub: https://github.com/ceavinrufus/agentpassport
Docs: https://agentpassport.fyi
