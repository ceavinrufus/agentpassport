from __future__ import annotations

import asyncio
import json
import re
import shlex
from typing import Any

from agentpassport.types import TaskEnvelope

from agentpassport_adapters.base import Adapter


class CliAdapter(Adapter):
    """Adapter that wraps a CLI tool as an agentpassport capability."""

    def __init__(self, command_template: str) -> None:
        """
        command_template uses {params.key} interpolation.
        Example: "curl -s {params.url}"
        """
        self.command_template = command_template

    async def execute(self, task: TaskEnvelope) -> dict[str, Any]:
        cmd = re.sub(
            r"\{params\.(\w+)\}",
            lambda m: shlex.quote(str(task.intent.params.get(m.group(1), ""))),
            self.command_template,
        )

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode().strip()

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"output": output, "exit_code": proc.returncode}
