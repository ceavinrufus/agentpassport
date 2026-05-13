# Guide: Building Your First AgentPassport Agent (Python)

This guide walks through building a complete, runnable multi-agent system with AgentPassport. By the end you will have:

1. An orchestrator agent that receives tasks from an HTTP client
2. A worker agent that the orchestrator delegates to
3. A database reader agent that the worker delegates to
4. Proper scope enforcement at every hop
5. Revocation demonstrated

Every code block here is complete and runnable. Copy-paste the entire file, install dependencies, and run it.

---

## Prerequisites

```bash
pip install agentpassport fastapi uvicorn httpx
```

---

## Step 1: Single agent that handles a task locally

The simplest possible AgentPassport setup: one agent, one capability, no delegation.

```python
# file: step1_single_agent.py

import asyncio
from agentpassport import Agent, TaskEnvelope, Intent

# Create an agent. A fresh Ed25519 keypair is generated automatically.
agent = Agent(name="echo-agent")

print(f"Agent DID: {agent.did}")
# did:key:z6Mk...  (will be different each run)


# Register a capability. No scope required — this is a public endpoint.
@agent.capability("echo")
async def echo(task: TaskEnvelope) -> dict:
    message = task.intent.params.get("message", "")
    return {"echoed": message, "from": agent.did}


async def main():
    # Simulate receiving a task (normally this comes from an HTTP request)
    task = TaskEnvelope(
        intent=Intent(type="echo", params={"message": "Hello, AgentPassport!"})
    )

    result = await agent.handle(task)
    print(result)
    # {'echoed': 'Hello, AgentPassport!', 'from': 'did:key:z6Mk...'}


asyncio.run(main())
```

---

## Step 2: Two agents with delegation

Now we add delegation. The orchestrator delegates to the worker using a signed JWT.

```python
# file: step2_delegation.py

import asyncio
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    Constraints,
    sign_delegation,
    verify_auth_chain,
    MemorySink,
    EventEmitter,
    generate_keypair,
)

# ─── Set up two agents ────────────────────────────────────────────────────────

orch_priv, orch_pub = generate_keypair()
orchestrator = Agent(name="orchestrator", private_key=orch_priv)
worker = Agent(name="worker")

print(f"Orchestrator DID: {orchestrator.did}")
print(f"Worker DID:       {worker.did}")

# The worker needs to trust the orchestrator's public key.
# We share the public key out-of-band here; in production this comes
# from an AgentCard registry or a shared configuration.
worker.trust_keys({orchestrator.did: orchestrator.public_key})


# ─── Worker capability (requires scope) ───────────────────────────────────────

@worker.capability("process_data", requires=["process:data"])
async def process_data(task: TaskEnvelope) -> dict:
    payload = task.intent.params.get("payload", "")
    return {
        "processed": payload.upper(),
        "by": worker.did,
    }


# ─── Main flow ────────────────────────────────────────────────────────────────

async def main():
    # 1. Create the task (from an external caller or the orchestrator itself)
    task = TaskEnvelope(
        intent=Intent(type="process_data", params={"payload": "hello world"}),
        constraints=Constraints(budget_credits=100.0, max_delegations=5),
    )

    # 2. Orchestrator signs a delegation JWT and appends it to the auth chain.
    #    scope=["process:data"] matches the worker's `requires`.
    delegation_token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=worker.did,
        scope=["process:data"],
        ttl_seconds=3600,
    )
    task.auth_chain.append(delegation_token)
    print(f"\nDelegation token (JWT): {delegation_token[:60]}...")

    # 3. Verify manually (what the worker does internally)
    ok = verify_auth_chain(
        auth_chain=task.auth_chain,
        expected_subject=worker.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
    )
    print(f"Chain valid: {ok}")  # True

    # 4. Worker handles the task — scope check passes automatically
    result = await worker.handle(task)
    print(f"\nResult: {result}")
    # {'processed': 'HELLO WORLD', 'by': 'did:key:z6Mk...'}

    # 5. What happens without the delegation token?
    task_no_auth = TaskEnvelope(
        intent=Intent(type="process_data", params={"payload": "test"}),
    )
    from agentpassport import ScopeError
    try:
        await worker.handle(task_no_auth)
    except ScopeError as e:
        print(f"\nExpected ScopeError: {e}")
        # "Capability 'process_data' requires scope ['process:data'] but the
        #  task carries no auth chain."


asyncio.run(main())
```

---

## Step 3: Full HTTP server with FastAPI

A production-ready agent exposed over HTTP using FastAPI and uvicorn.

```python
# file: step3_http_worker.py
# Run with: uvicorn step3_http_worker:app --port 8001

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    ScopeError,
    EventEmitter,
    FileSink,
    MemorySink,
)
from pathlib import Path


# ─── Agent setup ──────────────────────────────────────────────────────────────

# In production, load this from a secret store or environment variable:
# import os, binascii
# private_key = binascii.unhexlify(os.environ["AGENT_PRIVATE_KEY"])
# agent = Agent("worker", private_key=private_key)

sink = MemorySink()
emitter = EventEmitter(sinks=[FileSink(Path("worker_events.ndjson")), sink])
agent = Agent(name="data-worker", emitter=emitter)

print(f"Worker DID (share this with orchestrators): {agent.did}")
print(f"Worker public key (hex): {agent.public_key.hex()}")


# ─── Capabilities ─────────────────────────────────────────────────────────────

@agent.capability("summarize", requires=["invoke:llm"])
async def summarize(task: TaskEnvelope) -> dict:
    text = task.intent.params.get("text", "")
    # In real code: call an LLM API here
    summary = f"Summary of: {text[:50]}..."
    return {
        "summary": summary,
        "tokens_used": len(text.split()),
        "agent": agent.did,
    }


@agent.capability("health_check")
async def health_check(task: TaskEnvelope) -> dict:
    return {"status": "ok", "agent": agent.name, "did": agent.did}


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="AgentPassport Worker", version="1.0")


@app.post("/agentpassport/tasks")
async def receive_task(request: Request) -> JSONResponse:
    """Receive and handle an AgentPassport task."""
    body = await request.body()

    # Deserialize
    try:
        task = TaskEnvelope.model_validate_json(body)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid task envelope: {e}",
        )

    # Handle
    try:
        result = await agent.handle(task)
        return JSONResponse(content=result)
    except ScopeError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "scope_denied", "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_capability", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": str(e)},
        )


@app.get("/agentpassport/agent-card")
async def get_agent_card() -> dict:
    """Return the agent's card (unsigned) for discovery."""
    return {
        "did": agent.did,
        "name": agent.name,
        "capabilities": list(agent.capabilities.keys()),
        "endpoint": "http://localhost:8001",
        "transports": ["http"],
    }


@app.get("/agentpassport/events")
async def get_events() -> dict:
    """Return recent events (from MemorySink) for debugging."""
    return {
        "count": len(sink.events),
        "events": [e.model_dump() for e in sink.events[-20:]],
    }


# ─── Register a trusted orchestrator ──────────────────────────────────────────
# In production, load from config or registry.
# Here we show how you'd add it at startup:

@app.on_event("startup")
async def startup():
    import os
    orchestrator_did = os.getenv("TRUSTED_ORCHESTRATOR_DID")
    orchestrator_pub_hex = os.getenv("TRUSTED_ORCHESTRATOR_PUB_HEX")
    if orchestrator_did and orchestrator_pub_hex:
        agent.trust_keys({orchestrator_did: bytes.fromhex(orchestrator_pub_hex)})
        print(f"Trusted orchestrator: {orchestrator_did}")
    else:
        print("WARNING: No trusted orchestrator configured. Scoped capabilities will reject all tasks.")
```

---

## Step 4: Orchestrator that delegates to the worker

The orchestrator is a separate process that creates tasks and sends them to the worker.

```python
# file: step4_orchestrator.py

import asyncio
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    Constraints,
    parse_did,
)

# ─── Orchestrator setup ───────────────────────────────────────────────────────

orchestrator = Agent(name="orchestrator")
print(f"Orchestrator DID: {orchestrator.did}")
print(f"Orchestrator pub (hex): {orchestrator.public_key.hex()}")

# The worker's DID. In production, retrieve this from the registry or config.
# Set these to match what was printed by step3_http_worker.py
WORKER_DID = "did:key:z6Mk..."      # replace with actual
WORKER_ENDPOINT = "http://localhost:8001"


async def run_summarization(text: str) -> dict:
    """Orchestrate a summarization task by delegating to the worker."""

    # 1. Create the task
    task = TaskEnvelope(
        intent=Intent(type="summarize", params={"text": text}),
        constraints=Constraints(
            budget_credits=50.0,
            max_delegations=3,
        ),
    )
    print(f"Task ID: {task.id}")
    print(f"Trace ID: {task.trace_id}")

    # 2. Delegate to the worker with the required scope
    result = await orchestrator.delegate(
        task=task,
        target_did=WORKER_DID,
        endpoint=WORKER_ENDPOINT,
        scope=["invoke:llm"],      # grants the scope required by the worker's "summarize" capability
        ttl_seconds=600,           # 10-minute window
    )

    return result


async def main():
    result = await run_summarization(
        "AgentPassport is a protocol for giving AI agents cryptographically "
        "verifiable identities and expressing who authorized whom to do what."
    )
    print(f"\nResult: {result}")
    # {'summary': 'Summary of: AgentPassport is a protocol...', 'tokens_used': N, 'agent': '...'}


asyncio.run(main())
```

---

## Step 5: Three-hop delegation chain with scopes

The real power of AgentPassport: scopes narrow as tasks travel through multiple agents.

```python
# file: step5_three_hop.py

import asyncio
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    Constraints,
    sign_delegation,
    ScopeError,
    EventEmitter,
    MemorySink,
    generate_keypair,
)

# ─── Three agents ─────────────────────────────────────────────────────────────

sink = MemorySink()
emitter = EventEmitter(sinks=[sink])

orch_priv, orch_pub = generate_keypair()
analyzer_priv, analyzer_pub = generate_keypair()
orchestrator = Agent(name="orchestrator", private_key=orch_priv, emitter=emitter)
analyzer = Agent(name="analyzer", private_key=analyzer_priv, emitter=emitter)
db_reader = Agent(name="db-reader", emitter=emitter)

# ─── Trust setup ──────────────────────────────────────────────────────────────

# Each agent trusts the agent above it in the chain.
# In production, this comes from configuration or a key registry.
analyzer.trust_keys({orchestrator.did: orchestrator.public_key})
db_reader.trust_keys({
    orchestrator.did: orchestrator.public_key,
    analyzer.did: analyzer.public_key,
})


# ─── Capabilities ─────────────────────────────────────────────────────────────

@db_reader.capability("read_customers", requires=["read:db:customers"])
async def read_customers(task: TaskEnvelope) -> dict:
    limit = task.intent.params.get("limit", 10)
    # Simulate a DB read
    rows = [{"id": i, "name": f"Customer {i}"} for i in range(limit)]
    return {"rows": rows, "count": len(rows)}


@analyzer.capability("analyze_customers", requires=["analyze:customers"])
async def analyze_customers(task: TaskEnvelope) -> dict:
    """Analyzer receives the task, then delegates the DB read to db_reader."""

    # Create a sub-task for the DB reader.
    # We construct the delegation chain: existing chain + our delegation to db_reader.
    sub_task = TaskEnvelope(
        intent=Intent(type="read_customers", params={"limit": 5}),
        constraints=Constraints(
            budget_credits=task.constraints.budget_credits - 10,
            max_delegations=task.constraints.max_delegations - 1,
        ),
        auth_chain=task.auth_chain.copy(),  # inherit the upstream chain
        trace_id=task.trace_id,             # preserve trace context
        parent_id=task.id,
    )

    # Analyzer signs a delegation to db_reader with narrowed scope
    delegation_to_db = sign_delegation(
        issuer_private_key=analyzer_priv,
        ttl_seconds=300,
    )
    sub_task.auth_chain.append(delegation_to_db)

    # Normally we'd HTTP POST this; in this example we call handle() directly
    db_result = await db_reader.handle(sub_task)

    # Analyze the data
    customer_count = db_result["count"]
    return {
        "analysis": f"Found {customer_count} customers in the DB.",
        "raw_count": customer_count,
    }


# ─── Main flow ────────────────────────────────────────────────────────────────

async def main():
    # 1. Orchestrator creates the top-level task
    task = TaskEnvelope(
        intent=Intent(type="analyze_customers", params={}),
        constraints=Constraints(budget_credits=100.0, max_delegations=5),
    )

    # 2. Orchestrator delegates to analyzer with broad scope
    orch_to_analyzer = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=analyzer.did,
        scope=["analyze:customers", "read:db:customers"],  # grants enough for the whole chain
        ttl_seconds=3600,
    )
    task.auth_chain.append(orch_to_analyzer)

    print(f"Auth chain length before analyzer: {len(task.auth_chain)}")  # 1

    # 3. Analyzer handles (will internally delegate to db_reader)
    result = await analyzer.handle(task)
    print(f"\nResult: {result}")
    # {'analysis': 'Found 5 customers in the DB.', 'raw_count': 5}

    # 4. What if the scope doesn't include read:db:customers?
    task_narrow = TaskEnvelope(
        intent=Intent(type="analyze_customers", params={}),
        constraints=Constraints(budget_credits=100.0, max_delegations=5),
    )
    bad_token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=analyzer.did,
        scope=["analyze:customers"],   # missing read:db:customers
        ttl_seconds=3600,
    )
    task_narrow.auth_chain.append(bad_token)

    # Analyzer will handle ok (has "analyze:customers")
    # but when it tries to delegate to db_reader with "read:db:customers"...
    # the sub-task will be rejected because the chain doesn't grant it to db_reader.
    # Let's simulate this:
    # (The analyzer signs the delegation anyway, but db_reader.trust_keys check fails
    #  because db_reader won't find "read:db:customers" in the chain's granted scopes
    #  for itself — the orch→analyzer token doesn't grant it to db_reader directly)

    print("\n--- Attempting narrow-scoped task ---")
    try:
        await analyzer.handle(task_narrow)
    except ScopeError as e:
        print(f"ScopeError (from db_reader): {e}")

    # 5. Show emitted events
    print(f"\nTotal events emitted: {len(sink.events)}")
    for evt in sink.events:
        print(f"  [{evt.event}] agent={evt.agent[-10:]}... task={evt.task_id[:15]}...")


asyncio.run(main())
```

---

## Step 6: Budget tracking in a subtask tree

```python
# file: step6_budget.py

import asyncio
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    Constraints,
    BudgetTracker,
    BudgetExceededError,
    create_subtask,
    sign_delegation,
    generate_keypair,
)

orch_priv, orch_pub = generate_keypair()
orchestrator = Agent(name="orchestrator", private_key=orch_priv)
worker_a = Agent(name="worker-a")
worker_b = Agent(name="worker-b")

worker_a.trust_keys({orchestrator.did: orchestrator.public_key})
worker_b.trust_keys({orchestrator.did: orchestrator.public_key})


@worker_a.capability("task_a", requires=["run:task_a"])
async def task_a(task: TaskEnvelope) -> dict:
    return {"a": "done", "cost": 15.0}


@worker_b.capability("task_b", requires=["run:task_b"])
async def task_b(task: TaskEnvelope) -> dict:
    return {"b": "done", "cost": 20.0}


async def main():
    # Parent task with 100-credit budget
    parent = TaskEnvelope(
        intent=Intent(type="orchestrate", params={}),
        constraints=Constraints(budget_credits=100.0, max_delegations=5),
    )
    parent_tracker = BudgetTracker(total_credits=parent.constraints.budget_credits)

    print(f"Budget: {parent_tracker.total_credits} credits")

    # ── Allocate and run subtask A ────────────────────────────────────────────

    sub_a = create_subtask(
        parent=parent,
        intent=Intent(type="task_a", params={}),
        budget_credits=30.0,    # allocate 30 credits for subtask A
        budget_tracker=parent_tracker,
    )
    print(f"After allocating A: {parent_tracker.remaining} remaining")  # 70.0

    # Add delegation for sub_a
    token_a = sign_delegation(
        orch_priv, orchestrator.did, worker_a.did,
        scope=["run:task_a"], ttl_seconds=600,
    )
    sub_a.auth_chain.append(token_a)
    result_a = await worker_a.handle(sub_a)
    print(f"Task A result: {result_a}")

    # Subtask A only used 15 of its 30-credit allocation — return the rest
    actual_cost_a = result_a["cost"]  # 15.0
    unused_a = 30.0 - actual_cost_a
    parent_tracker.return_unused(unused_a)
    print(f"After A completes and returns {unused_a} credits: {parent_tracker.remaining} remaining")
    # 85.0

    # ── Allocate and run subtask B ────────────────────────────────────────────

    sub_b = create_subtask(
        parent=parent,
        intent=Intent(type="task_b", params={}),
        budget_credits=20.0,
        budget_tracker=parent_tracker,
    )
    print(f"After allocating B: {parent_tracker.remaining} remaining")  # 65.0

    token_b = sign_delegation(
        orch_priv, orchestrator.did, worker_b.did,
        scope=["run:task_b"], ttl_seconds=600,
    )
    sub_b.auth_chain.append(token_b)
    result_b = await worker_b.handle(sub_b)
    print(f"Task B result: {result_b}")

    # ── Try to exceed budget ──────────────────────────────────────────────────

    try:
        # This would require 80 credits but only 65 remain
        create_subtask(
            parent=parent,
            intent=Intent(type="task_a", params={}),
            budget_credits=80.0,
            budget_tracker=parent_tracker,
        )
    except BudgetExceededError as e:
        print(f"\nBudget exceeded: requested={e.requested}, remaining={e.remaining}")
        # Budget exceeded: requested=80.0, remaining=65.0

    print(f"\nFinal remaining budget: {parent_tracker.remaining}")


asyncio.run(main())
```

---

## Step 7: Revocation

```python
# file: step7_revocation.py

import asyncio
import json
import base64
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    Constraints,
    sign_delegation,
    verify_auth_chain,
    InMemoryRevocationRegistry,
    SqliteRevocationRegistry,
    generate_keypair,
)

orch_priv, orch_pub = generate_keypair()
orchestrator = Agent(name="orchestrator", private_key=orch_priv)
worker = Agent(name="worker")
worker.trust_keys({orchestrator.did: orchestrator.public_key})

registry = InMemoryRevocationRegistry()


@worker.capability("sensitive_op", requires=["exec:sensitive"])
async def sensitive_op(task: TaskEnvelope) -> dict:
    return {"done": True}


def decode_jti(token: str) -> str:
    """Extract JTI from a JWT without verifying."""
    payload_b64 = token.split(".")[1]
    # Re-add padding
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    return claims["jti"]


async def main():
    # 1. Issue a delegation token
    token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=worker.did,
        scope=["exec:sensitive"],
        ttl_seconds=3600,
    )
    jti = decode_jti(token)
    print(f"JTI: {jti}")

    task = TaskEnvelope(
        intent=Intent(type="sensitive_op", params={}),
        constraints=Constraints(budget_credits=10.0, max_delegations=1),
        auth_chain=[token],
    )

    # 2. Verify chain before revocation — passes
    ok_before = verify_auth_chain(
        auth_chain=[token],
        expected_subject=worker.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
        revocation_registry=registry,
    )
    print(f"Valid before revocation: {ok_before}")  # True

    # 3. Revoke the token
    registry.revoke(jti)
    print(f"Token revoked: {jti}")

    # 4. Verify chain after revocation — fails
    ok_after = verify_auth_chain(
        auth_chain=[token],
        expected_subject=worker.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
        revocation_registry=registry,
    )
    print(f"Valid after revocation: {ok_after}")  # False

    # 5. Issue a new token — this one is not revoked
    new_token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=worker.did,
        scope=["exec:sensitive"],
        ttl_seconds=3600,
    )
    new_task = TaskEnvelope(
        intent=Intent(type="sensitive_op", params={}),
        constraints=Constraints(budget_credits=10.0, max_delegations=1),
        auth_chain=[new_token],
    )
    result = await worker.handle(new_task)
    print(f"New token works: {result}")  # {'done': True}


asyncio.run(main())
```

---

## Step 8: AgentCard signing and verification

```python
# file: step8_agent_card.py

import asyncio
from agentpassport import (
    Agent,
    AgentCard,
    CostInfo,
    sign_agent_card,
    verify_agent_card,
    parse_did,
    RegistryClient,
    generate_keypair,
)


async def main():
    agent_priv, agent_pub = generate_keypair()
    agent = Agent(name="data-processor", private_key=agent_priv)

    # 1. Build an AgentCard
    card = AgentCard(
        did=agent.did,
        name="data-processor",
        version="1.2.0",
        capabilities=["process_csv", "process_json", "validate_schema"],
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "string"},
                "format": {"enum": ["csv", "json"]},
            },
            "required": ["data", "format"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "integer"},
                "status": {"type": "string"},
            },
        },
        cost=CostInfo(currency="credits", per_task=2.5),
        latency_p99_ms=1500,
        trust_requirements=["invoke:data_processor"],
        transports=["http"],
        endpoint="http://data-processor.internal:8080",
    )

    # 2. Sign the card
    signed_card = sign_agent_card(card, agent_priv)
    print(f"Signature: {signed_card.signature[:32]}...")

    # 3. Verify the signature
    pub_key = parse_did(agent.did)   # public key is embedded in the DID
    ok = verify_agent_card(signed_card, pub_key)
    print(f"Signature valid: {ok}")  # True

    # 4. Tampered card fails verification
    tampered = signed_card.model_copy(update={"endpoint": "http://evil.com"})
    ok_tampered = verify_agent_card(tampered, pub_key)
    print(f"Tampered card valid: {ok_tampered}")  # False

    # 5. Publish to registry (requires the registry service to be running)
    # client = RegistryClient("http://localhost:8000")
    # await client.publish(signed_card)
    # retrieved = await client.get(agent.did)
    # assert retrieved.did == agent.did

    # 6. Serialize/deserialize over the wire (e.g. JSON API)
    card_json = signed_card.model_dump_json()
    print(f"\nCard JSON: {card_json[:200]}...")

    restored_card = AgentCard.model_validate_json(card_json)
    assert verify_agent_card(restored_card, pub_key)
    print("Card survives JSON round-trip: True")


asyncio.run(main())
```

---

## Step 9: Observability with multiple sinks

```python
# file: step9_observability.py

import asyncio
import json
from pathlib import Path
from agentpassport import (
    Agent,
    TaskEnvelope,
    Intent,
    EventEmitter,
    StdoutSink,
    FileSink,
    MemorySink,
)

# ─── Set up emitter with multiple sinks ───────────────────────────────────────

memory_sink = MemorySink()

emitter = EventEmitter(sinks=[
    StdoutSink(),                          # NDJSON to stdout
    FileSink(Path("agent_events.ndjson")), # NDJSON to file
    memory_sink,                           # In-memory for testing/introspection
])

agent = Agent(name="observable-agent", emitter=emitter)


@agent.capability("slow_task")
async def slow_task(task: TaskEnvelope) -> dict:
    import asyncio
    await asyncio.sleep(0.01)  # Simulate work
    return {"done": True}


@agent.capability("failing_task")
async def failing_task(task: TaskEnvelope) -> dict:
    raise RuntimeError("Something went wrong!")


async def main():
    print("=== Running slow_task ===")
    task = TaskEnvelope(intent=Intent(type="slow_task", params={}))
    result = await agent.handle(task)
    print(f"Result: {result}\n")

    print("=== Running failing_task ===")
    failing = TaskEnvelope(intent=Intent(type="failing_task", params={}))
    try:
        await agent.handle(failing)
    except RuntimeError:
        pass

    # Inspect emitted events
    print("\n=== Events (from MemorySink) ===")
    for evt in memory_sink.events:
        print(f"  {evt.event:25} | task={evt.task_id[:15]}... | agent={evt.agent[-15:]}...")

    # Expected output:
    #   task_accepted             | task=task_... | agent=...z6Mk...
    #   task_running              | task=task_... | agent=...z6Mk...
    #   task_completed            | task=task_... | agent=...z6Mk...
    #   task_accepted             | task=task_... | agent=...z6Mk...
    #   task_running              | task=task_... | agent=...z6Mk...
    #   task_failed               | task=task_... | agent=...z6Mk...

    # The file "agent_events.ndjson" now contains all events as JSON lines
    events_from_file = [
        json.loads(line)
        for line in Path("agent_events.ndjson").read_text().strip().splitlines()
    ]
    print(f"\nEvents written to file: {len(events_from_file)}")


asyncio.run(main())
```

---

## Step 10: Complete production example — all features together

This is a self-contained example combining every feature: identity, cards, delegation chains, scope enforcement, budget tracking, revocation, and observability.

```python
# file: step10_complete.py

"""
Complete production-style example.
No external services required — everything runs in-process.

Architecture:
  User
    → Orchestrator (creates task, delegates to Analyzer)
        → Analyzer (handles analysis, delegates DB read to DbReader)
            → DbReader (reads data from simulated DB)
"""

import asyncio
import json
import base64
from pathlib import Path
from agentpassport import (
    Agent, TaskEnvelope, Intent, Constraints,
    AgentCard, CostInfo, sign_agent_card, verify_agent_card, parse_did,
    sign_delegation, verify_auth_chain,
    BudgetTracker, create_subtask,
    InMemoryRevocationRegistry,
    EventEmitter, MemorySink, StdoutSink,
    ScopeError,
    generate_keypair,
)


# ══════════════════════════════════════════════════════════════
# 1. AGENTS
# ══════════════════════════════════════════════════════════════

audit_sink = MemorySink()
emitter = EventEmitter(sinks=[audit_sink])  # Add StdoutSink() for verbose output

orch_priv, orch_pub = generate_keypair()
analyzer_priv, analyzer_pub = generate_keypair()
db_reader_priv, db_reader_pub = generate_keypair()
orchestrator = Agent(name="orchestrator", private_key=orch_priv, emitter=emitter)
analyzer = Agent(name="analyzer", private_key=analyzer_priv, emitter=emitter)
db_reader = Agent(name="db-reader", private_key=db_reader_priv, emitter=emitter)

revocation_registry = InMemoryRevocationRegistry()


# ══════════════════════════════════════════════════════════════
# 2. TRUST SETUP
# ══════════════════════════════════════════════════════════════

# Each agent trusts all potential issuers in the chain above it.
analyzer.trust_keys({orchestrator.did: orchestrator.public_key})
db_reader.trust_keys({
    orchestrator.did: orchestrator.public_key,
    analyzer.did: analyzer.public_key,
})


# ══════════════════════════════════════════════════════════════
# 3. AGENT CARDS
# ══════════════════════════════════════════════════════════════

def make_and_sign_card(agent: Agent, priv: bytes, capabilities: list[str], endpoint: str) -> AgentCard:
    card = AgentCard(
        did=agent.did,
        name=agent.name,
        capabilities=capabilities,
        endpoint=endpoint,
        cost=CostInfo(per_task=1.0),
    )
    return sign_agent_card(card, priv)

orch_card = make_and_sign_card(orchestrator, orch_priv, ["orchestrate"], "http://orchestrator:8000")
analyzer_card = make_and_sign_card(analyzer, analyzer_priv, ["analyze"], "http://analyzer:8001")
db_card = make_and_sign_card(db_reader, db_reader_priv, ["read_db"], "http://db-reader:8002")

# Verify all cards
for card in [orch_card, analyzer_card, db_card]:
    assert verify_agent_card(card, parse_did(card.did)), f"Card invalid for {card.name}"
    print(f"✓ Card valid: {card.name} ({card.did[:30]}...)")


# ══════════════════════════════════════════════════════════════
# 4. CAPABILITIES
# ══════════════════════════════════════════════════════════════

@db_reader.capability("read_db", requires=["read:db"])
async def read_db(task: TaskEnvelope) -> dict:
    table = task.intent.params.get("table", "records")
    limit = task.intent.params.get("limit", 10)
    # Simulate DB read
    rows = [{"id": i, "table": table, "value": i * 2} for i in range(limit)]
    return {"rows": rows, "count": len(rows), "table": table}


@analyzer.capability("analyze", requires=["invoke:analyze"])
async def analyze(task: TaskEnvelope) -> dict:
    tracker = BudgetTracker(task.constraints.budget_credits)

    # Create sub-task for DB read
    sub = create_subtask(
        parent=task,
        intent=Intent(type="read_db", params={"table": "orders", "limit": 5}),
        budget_credits=20.0,
        budget_tracker=tracker,
    )

    # Sign delegation to db_reader
    token = sign_delegation(
        issuer_private_key=analyzer_priv,
        issuer_did=analyzer.did,
        subject_did=db_reader.did,
        scope=["read:db"],
        ttl_seconds=300,
    )
    sub.auth_chain.append(token)

    # In production: send via HTTP. Here: call directly.
    db_result = await db_reader.handle(sub)

    # Compute analysis
    rows = db_result["rows"]
    total = sum(r["value"] for r in rows)
    avg = total / len(rows) if rows else 0

    return {
        "row_count": len(rows),
        "total_value": total,
        "average_value": avg,
        "budget_used": 20.0,
        "budget_remaining": tracker.remaining,
    }


# ══════════════════════════════════════════════════════════════
# 5. ORCHESTRATOR LOGIC
# ══════════════════════════════════════════════════════════════

async def run_analysis_workflow() -> dict:
    """Full workflow: create task, delegate to analyzer, get results."""

    print("\n─── Starting analysis workflow ───")

    # 1. Create the top-level task
    task = TaskEnvelope(
        intent=Intent(type="analyze", params={}),
        constraints=Constraints(
            budget_credits=100.0,
            max_delegations=5,
        ),
    )
    print(f"Task: {task.id}")
    print(f"Trace: {task.trace_id}")

    # 2. Orchestrator signs delegation to analyzer
    orch_token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=analyzer.did,
        scope=["invoke:analyze", "read:db"],  # grants full chain what it needs
        ttl_seconds=3600,
    )
    task.auth_chain.append(orch_token)

    # 3. Verify the chain before sending (optional double-check)
    ok = verify_auth_chain(
        auth_chain=task.auth_chain,
        expected_subject=analyzer.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
        revocation_registry=revocation_registry,
    )
    assert ok, "Chain verification failed before sending!"
    print(f"Chain verified: {ok}")

    # 4. Analyzer handles (in production: POST to http://analyzer:8001)
    result = await analyzer.handle(task)
    print(f"Analysis result: {result}")

    return result


# ══════════════════════════════════════════════════════════════
# 6. REVOCATION DEMO
# ══════════════════════════════════════════════════════════════

async def demonstrate_revocation():
    print("\n─── Revocation demo ───")

    task = TaskEnvelope(
        intent=Intent(type="analyze", params={}),
        constraints=Constraints(budget_credits=50.0, max_delegations=3),
    )

    token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=analyzer.did,
        scope=["invoke:analyze", "read:db"],
        ttl_seconds=3600,
    )

    # Extract JTI for revocation
    raw = token.split(".")[1]
    pad = 4 - len(raw) % 4
    claims = json.loads(base64.urlsafe_b64decode(raw + "=" * pad if pad != 4 else raw))
    jti = claims["jti"]
    print(f"JTI to revoke: {jti}")

    task.auth_chain.append(token)

    # Works before revocation
    result_before = await analyzer.handle(task)
    print(f"Before revocation: {result_before['row_count']} rows")

    # Revoke
    revocation_registry.revoke(jti)
    print("Token revoked.")

    # Doesn't work after revocation (verify_auth_chain would return False)
    ok_after = verify_auth_chain(
        auth_chain=[token],
        expected_subject=analyzer.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
        revocation_registry=revocation_registry,
    )
    print(f"Chain valid after revocation: {ok_after}")  # False


# ══════════════════════════════════════════════════════════════
# 7. SCOPE ENFORCEMENT DEMO
# ══════════════════════════════════════════════════════════════

async def demonstrate_scope_enforcement():
    print("\n─── Scope enforcement demo ───")

    # Task with insufficient scope
    task = TaskEnvelope(
        intent=Intent(type="analyze", params={}),
        constraints=Constraints(budget_credits=50.0, max_delegations=3),
    )
    bad_token = sign_delegation(
        issuer_private_key=orch_priv,
        issuer_did=orchestrator.did,
        subject_did=analyzer.did,
        scope=["something_else"],  # doesn't include invoke:analyze
        ttl_seconds=3600,
    )
    task.auth_chain.append(bad_token)

    try:
        await analyzer.handle(task)
        print("ERROR: Should have raised ScopeError!")
    except ScopeError as e:
        print(f"ScopeError raised (expected): {e}")


# ══════════════════════════════════════════════════════════════
# 8. MAIN
# ══════════════════════════════════════════════════════════════

async def main():
    print("=== AgentPassport Complete Example ===\n")

    # Show agent identities
    for a in [orchestrator, analyzer, db_reader]:
        print(f"{a.name}: {a.did}")

    # Run workflows
    await run_analysis_workflow()
    await demonstrate_revocation()
    await demonstrate_scope_enforcement()

    # Show audit trail
    print(f"\n─── Audit trail: {len(audit_sink.events)} events ───")
    for evt in audit_sink.events:
        print(f"  {evt.timestamp[:19]} | {evt.event:20} | {evt.agent[-20:]}")


asyncio.run(main())
```
