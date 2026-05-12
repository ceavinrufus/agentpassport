import pytest
from agentpassport.task.budget import BudgetExceededError, BudgetTracker


def test_budget_spend():
    bt = BudgetTracker(total_credits=10.0)
    bt.spend(3.0)
    assert bt.remaining == 7.0


def test_budget_exceeded():
    bt = BudgetTracker(total_credits=5.0)
    bt.spend(3.0)
    with pytest.raises(BudgetExceededError):
        bt.spend(3.0)  # Would exceed


def test_budget_allocate_for_subtask():
    bt = BudgetTracker(total_credits=10.0)
    sub_budget = bt.allocate(7.0)
    assert sub_budget == 7.0
    assert bt.remaining == 3.0


def test_budget_return_unused():
    bt = BudgetTracker(total_credits=10.0)
    bt.allocate(7.0)
    bt.return_unused(2.0)
    assert bt.remaining == 5.0
