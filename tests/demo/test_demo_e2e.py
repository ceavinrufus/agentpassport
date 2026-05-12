"""End-to-end test for the 3-agent incident investigation demo (mock fallbacks only)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentpassport import Intent, TaskEnvelope
from demo.orchestrator import orchestrator


@pytest.fixture(autouse=True)
def _no_pup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure pup is treated as not found so Datadog agent uses mock data."""
    import asyncio

    async def _fake_create_subprocess_exec(*args, **kwargs):  # noqa: ANN002
        raise FileNotFoundError("pup not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)


@pytest.fixture(autouse=True)
def _no_lark_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure Lark env vars are absent so Lark agent uses mock data."""
    monkeypatch.delenv("LARK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)


async def test_incident_investigation_returns_both_agents() -> None:
    task = TaskEnvelope(
        intent=Intent(
            type="run_incident_investigation",
            params={"incident_id": "INC-001", "title": "High CPU on prod"},
        )
    )

    result = await orchestrator.handle(task)

    assert result["incident_id"] == "INC-001"
    assert result["datadog"]["source"] == "datadog"
    assert result["lark"]["source"] == "lark"


async def test_datadog_mock_fallback() -> None:
    task = TaskEnvelope(
        intent=Intent(
            type="run_incident_investigation",
            params={"incident_id": "INC-002", "title": "Memory spike"},
        )
    )

    result = await orchestrator.handle(task)

    dd = result["datadog"]
    assert dd["authentic"] is False
    assert isinstance(dd["metrics"], list)
    assert len(dd["metrics"]) > 0


async def test_lark_mock_fallback() -> None:
    task = TaskEnvelope(
        intent=Intent(
            type="run_incident_investigation",
            params={"incident_id": "INC-003", "title": "Disk full"},
        )
    )

    result = await orchestrator.handle(task)

    lark = result["lark"]
    assert lark["notified"] is False
    assert lark["channel"] == "mock"
