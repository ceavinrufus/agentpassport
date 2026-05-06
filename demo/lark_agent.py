"""Lark APS agent — notifies team via webhook or returns mock data."""

from __future__ import annotations

import json
import os
from typing import Any

from aps_sdk import Agent, TaskEnvelope

lark_agent = Agent(name="lark-agent")


@lark_agent.capability("notify_team")
async def notify_team(task: TaskEnvelope) -> dict[str, Any]:
    summary = task.intent.params.get("summary", "Incident detected.")
    incident_id = task.intent.params.get("incident_id", "unknown")

    webhook_url = os.environ.get("LARK_WEBHOOK_URL")

    if not webhook_url:
        return {
            "source": "lark",
            "notified": False,
            "channel": "mock",
            "message": f"[MOCK] Would notify team about {incident_id}: {summary}",
        }

    channel = "webhook"
    try:
        import urllib.request

        payload = json.dumps(
            {
                "msg_type": "text",
                "content": {"text": f"[APS Alert] {incident_id}: {summary}"},
            }
        ).encode()

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            notified = resp.status == 200
    except Exception:  # noqa: BLE001
        notified = False

    return {
        "source": "lark",
        "notified": notified,
        "channel": channel,
        "message": f"Notified team about {incident_id}: {summary}",
    }
