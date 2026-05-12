from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentpassport.types import TaskEnvelope


class Adapter(ABC):
    @abstractmethod
    async def execute(self, task: TaskEnvelope) -> dict[str, Any]:
        """Execute a task through the adapted service."""
        ...
