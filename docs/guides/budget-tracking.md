# Budget Tracking

AgentPassport's `BudgetTracker` enforces credit limits on task execution and subtask delegation. It prevents runaway spending by raising `BudgetExceededError` before any amount is deducted that would exceed the available balance.

---

## Core concepts

Credits are an abstract unit defined by you and your orchestrator. Common mappings:

- 1 credit = $0.01 of LLM spend
- 1 credit = 1 API call
- 1 credit = 1 database row read

The initial budget comes from `TaskEnvelope.constraints.budget_credits` (default `100.0`). Each agent is responsible for tracking its own spend against this budget using a `BudgetTracker` instance.

---

## BudgetTracker

```python
from agentpassport.task.budget import BudgetTracker, BudgetExceededError

tracker = BudgetTracker(total_credits=50.0)
print(tracker.remaining)  # 50.0
```

### Constructor

| Parameter | Type | Description |
|-----------|------|-------------|
| `total_credits` | `float` | Maximum credits available for this task |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `total_credits` | `float` | The budget ceiling set at construction |
| `spent` | `float` | Credits consumed so far |
| `remaining` | `float` | `total_credits - spent` |

---

## Synchronous methods

### `spend(amount)`

Deducts `amount` from the budget immediately. Use this for work the current agent does itself (LLM calls, database reads, etc.).

```python
tracker.spend(2.5)   # deduct 2.5 credits
print(tracker.remaining)  # 47.5
```

Raises `BudgetExceededError` if `amount > remaining`. Raises `ValueError` if `amount < 0`.

### `allocate(amount) -> float`

Reserves `amount` for a subtask. Returns the allocated amount. The parent's `remaining` shrinks immediately, so the subtask cannot overspend the parent.

```python
allocated = tracker.allocate(10.0)
# Pass allocated to the subtask's Constraints.budget_credits
```

Raises `BudgetExceededError` if `amount > remaining`.

### `return_unused(amount)`

Returns unspent credits from a completed subtask back to the parent budget.

```python
# Subtask was allocated 10 but only used 6
tracker.return_unused(4.0)
print(tracker.remaining)  # goes up by 4
```

`return_unused` never lets `spent` go below 0, even if you return more than was allocated.

---

## Async methods

The async variants acquire an `asyncio.Lock` before modifying `spent`. Use these whenever your agent handles multiple tasks concurrently with a shared tracker.

| Method | Equivalent sync method |
|--------|------------------------|
| `await tracker.async_spend(amount)` | `spend(amount)` |
| `await tracker.async_allocate(amount)` | `allocate(amount)` |
| `await tracker.async_return_unused(amount)` | `return_unused(amount)` |

```python
async def run_task(tracker: BudgetTracker):
    await tracker.async_spend(5.0)
    # safe to call concurrently from multiple coroutines
```

---

## BudgetExceededError

Raised by `spend()`, `allocate()`, and their async variants when a requested amount would exceed the remaining budget.

```python
from agentpassport.task.budget import BudgetExceededError

try:
    tracker.spend(9999.0)
except BudgetExceededError as e:
    print(e.requested)   # 9999.0
    print(e.remaining)   # whatever was left
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `requested` | `float` | The amount that was requested |
| `remaining` | `float` | The budget remaining at the time of the error |

---

## Example: orchestrator with sub-agents

The following example shows a root orchestrator with a 100-credit budget delegating subtasks to two specialised agents, each with a carved-out share of the budget.

```python
import asyncio
from agentpassport import Agent, generate_keypair, did_from_public_key, sign_delegation
from agentpassport.task.budget import BudgetTracker, BudgetExceededError
from agentpassport.types.task import TaskEnvelope, Intent, Constraints

# --- Create orchestrator and sub-agent identities ---
orch_priv, orch_pub = generate_keypair()
orch_did = did_from_public_key(orch_pub)

search_priv, search_pub = generate_keypair()
search_did = did_from_public_key(search_pub)

summarise_priv, summarise_pub = generate_keypair()
summarise_did = did_from_public_key(summarise_pub)

# --- Orchestrator logic ---
async def orchestrate(query: str) -> dict:
    # Root budget: 100 credits
    root_tracker = BudgetTracker(total_credits=100.0)

    # Allocate 40 credits for the search subtask
    search_budget = root_tracker.allocate(40.0)

    search_task = TaskEnvelope(
        intent=Intent(type="web_search", params={"query": query}),
        constraints=Constraints(budget_credits=search_budget),
        auth_chain=[
            sign_delegation(
                orch_priv,
                orch_did,
                search_did,
                scopes=["read:web"],
                ttl_seconds=300,
            )
        ],
    )

    # (Send search_task to the search agent; receive result)
    search_result = {"snippets": ["..."], "credits_used": 12.0}

    # Return unused budget from the search subtask
    root_tracker.return_unused(search_budget - search_result["credits_used"])
    print(f"After search: {root_tracker.remaining:.1f} credits remaining")

    # Allocate up to 30 credits for the summarise subtask
    try:
        summarise_budget = root_tracker.allocate(30.0)
    except BudgetExceededError as e:
        return {"error": f"Not enough budget for summarise: {e.remaining} remaining"}

    summarise_task = TaskEnvelope(
        intent=Intent(type="summarise", params={"snippets": search_result["snippets"]}),
        constraints=Constraints(budget_credits=summarise_budget),
        auth_chain=[
            sign_delegation(
                orch_priv,
                orch_did,
                summarise_did,
                scopes=["invoke:llm"],
                ttl_seconds=300,
            )
        ],
    )

    # (Send summarise_task to the summarise agent; receive result)
    summarise_result = {"summary": "The answer is...", "credits_used": 8.0}

    root_tracker.return_unused(summarise_budget - summarise_result["credits_used"])
    print(f"Final budget used: {root_tracker.spent:.1f} / {root_tracker.total_credits:.1f}")

    return {"summary": summarise_result["summary"]}

asyncio.run(orchestrate("latest AI agent research"))
```

---

## Using BudgetTracker inside a capability handler

```python
@agent.capability("process_batch", requires=["read:db"])
async def process_batch(task: TaskEnvelope):
    tracker = BudgetTracker(total_credits=task.constraints.budget_credits)

    results = []
    for item_id in task.intent.params["item_ids"]:
        try:
            await tracker.async_spend(1.0)   # 1 credit per item
        except BudgetExceededError:
            break  # stop processing when budget runs out

        result = await fetch_item(item_id)
        results.append(result)

    return {"results": results, "credits_used": tracker.spent}
```

---

## Budget and the TaskEnvelope

`TaskEnvelope.constraints.budget_credits` carries the budget ceiling for the task. When creating a subtask with `create_subtask()`, this field is automatically set to the allocated amount:

```python
# Inside a capability handler
subtask = task.create_subtask(
    intent=Intent(type="sub_capability", params={...}),
    budget_credits=20.0,   # carved from parent's budget
    signing_key=agent.private_key,
    issuer_did=agent.did,
    subject_did=sub_agent_did,
    scopes=["invoke:llm"],
)
```

Always call `return_unused()` after the subtask completes to reclaim unspent credits for the parent task.
