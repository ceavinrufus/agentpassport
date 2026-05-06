from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aps_sdk.types.task import TaskEnvelope


class Transport(ABC):
    @abstractmethod
    async def send(self, task: TaskEnvelope, endpoint: str) -> dict[str, Any]:
        """Send a task to a remote agent and return the result."""
        ...

    @abstractmethod
    def serialize(self, task: TaskEnvelope) -> bytes:
        """Serialize a task envelope to bytes for transmission."""
        ...

    @abstractmethod
    def deserialize(self, data: bytes) -> TaskEnvelope:
        """Deserialize bytes back into a TaskEnvelope."""
        ...
