"""Orchestrator APS agent — coordinates Datadog + Lark agents in-process."""

from __future__ import annotations

from typing import Any

from aps_sdk import Agent, Intent, TaskEnvelope

from demo.datadog_agent import datadog_agent
from demo.lark_agent import lark_agent

orchestrator = Agent(name="orchestrator")


@orchestrator.capability("run_incident_investigation")
async def run_incident_investigation(task: TaskEnvelope) -> dict[str, Any]:
    incident_id = task.intent.params.get("incident_id", "unknown")
    title = task.intent.params.get("title", "Unknown incident")

    # Sub-task 1: investigate via Datadog
    dd_task = TaskEnvelope(
        parent_id=task.id,
        trace_id=task.trace_id,
        intent=Intent(
            type="investigate_incident",
            params={"incident_id": incident_id, "title": title},
        ),
    )
    dd_result = await datadog_agent.handle(dd_task)

    # Sub-task 2: notify team via Lark (pass Datadog summary)
    lark_task = TaskEnvelope(
        parent_id=task.id,
        trace_id=task.trace_id,
        intent=Intent(
            type="notify_team",
            params={
                "incident_id": incident_id,
                "summary": dd_result.get("summary", title),
            },
        ),
    )
    lark_result = await lark_agent.handle(lark_task)

    return {
        "incident_id": incident_id,
        "datadog": dd_result,
        "lark": lark_result,
    }
