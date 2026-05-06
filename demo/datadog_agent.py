"""Datadog APS agent — investigates incidents via pup CLI or returns mock data."""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from aps_sdk import Agent, TaskEnvelope

datadog_agent = Agent(name="datadog-agent")


@datadog_agent.capability("investigate_incident")
async def investigate_incident(task: TaskEnvelope) -> dict[str, Any]:
    incident_id = task.intent.params.get("incident_id", "unknown")
    title = task.intent.params.get("title", "Unknown incident")

    # Check pup auth status
    authenticated = False
    try:
        proc = await asyncio.create_subprocess_exec(
            "pup",
            "auth",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await proc.communicate()
        authenticated = proc.returncode == 0
    except FileNotFoundError:
        authenticated = False

    if not authenticated:
        return {
            "source": "datadog",
            "authentic": False,
            "metrics": [
                {"metric": "system.cpu.user", "value": 87.3, "unit": "%"},
                {"metric": "system.load.1", "value": 12.4, "unit": "load"},
            ],
            "summary": f"[MOCK] High CPU detected for {incident_id}: {title}. CPU at 87.3%.",
        }

    # Run pup metrics query
    metrics: list[dict] = []
    try:
        proc = await asyncio.create_subprocess_exec(
            "pup",
            "metrics",
            "query",
            "--query",
            "avg:system.cpu.user{*}",
            "--from",
            "1h",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(stdout.decode())
            metrics = data if isinstance(data, list) else [data]
        else:
            metrics = [{"metric": "system.cpu.user", "value": None, "error": "query failed"}]
    except Exception as exc:  # noqa: BLE001
        metrics = [{"metric": "system.cpu.user", "error": str(exc)}]

    summary = (
        f"Datadog metrics retrieved for {incident_id}: {title}. {len(metrics)} series returned."
    )
    return {
        "source": "datadog",
        "authentic": True,
        "metrics": metrics,
        "summary": summary,
    }
