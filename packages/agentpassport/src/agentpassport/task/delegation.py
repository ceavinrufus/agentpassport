from __future__ import annotations

from agentpassport.task.budget import BudgetTracker
from agentpassport.types.task import Constraints, Intent, TaskEnvelope


def create_subtask(
    parent: TaskEnvelope,
    intent: Intent,
    budget_credits: float,
    budget_tracker: BudgetTracker,
) -> TaskEnvelope:
    """Create a child task with budget allocated from parent."""
    if parent.constraints.max_delegations <= 0:
        raise ValueError("Cannot delegate: max_delegations exhausted")
    budget_tracker.allocate(budget_credits)

    return TaskEnvelope(
        parent_id=parent.id,
        intent=intent,
        constraints=Constraints(
            budget_credits=budget_credits,
            deadline_ms=parent.constraints.deadline_ms,
            max_delegations=parent.constraints.max_delegations - 1,
            allowed_capabilities=parent.constraints.allowed_capabilities,
            denied_capabilities=parent.constraints.denied_capabilities,
        ),
        auth_chain=parent.auth_chain.copy(),
        trace_id=parent.trace_id,
        transport=parent.transport,
    )
