"""Run the 3-agent incident investigation demo."""

from __future__ import annotations

import asyncio
import json

from aps_sdk import Intent, TaskEnvelope

from demo.orchestrator import orchestrator


async def main() -> None:
    task = TaskEnvelope(
        intent=Intent(
            type="run_incident_investigation",
            params={"incident_id": "INC-001", "title": "High CPU on prod"},
        )
    )

    print("Running incident investigation demo...\n")
    result = await orchestrator.handle(task)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
