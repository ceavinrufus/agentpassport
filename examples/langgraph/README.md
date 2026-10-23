# LangGraph example

A research graph with a signed delegation chain and a scope check on a tool.

```
orchestrator --read:web--> researcher --read:web--> writer
                                                    |
                                        search_web    (allowed)
                                        save_article  (denied: needs write:db)
```

The writer is a tool-calling node. The model here is a stub: it always calls `search_web` and `save_article`, then stops. Swap `writer_node` for a real chat model bound to the same tools when you want a live model. This file does not call an LLM API and does not need a key.

`save_article` is rejected by the writer agent's scope check before the capability handler runs.

## Run

From the repository root:

```bash
uv venv --python 3.12 /tmp/agentpassport-example-langgraph
uv pip install --python /tmp/agentpassport-example-langgraph/bin/python \
  -e packages/agentpassport \
  -r examples/langgraph/requirements.txt
/tmp/agentpassport-example-langgraph/bin/python examples/langgraph/research_pipeline.py
```

Outside this repo, install the published SDK yourself (`pip install agentpassport`) and keep the requirements in `requirements.txt`.

The script exits 0 only when the two-hop chain verifies, `search_web` returns notes, and `save_article` is denied without running its handler.
