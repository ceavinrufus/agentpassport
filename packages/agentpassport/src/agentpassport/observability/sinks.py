from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path

from agentpassport.types.events import ObservabilityEvent


class Sink(ABC):
    @abstractmethod
    def write(self, event: ObservabilityEvent) -> None: ...


class StdoutSink(Sink):
    def write(self, event: ObservabilityEvent) -> None:
        sys.stdout.write(event.model_dump_json() + "\n")
        sys.stdout.flush()


class FileSink(Sink):
    def __init__(self, path: Path):
        self.path = path

    def write(self, event: ObservabilityEvent) -> None:
        with self.path.open("a") as f:
            f.write(event.model_dump_json() + "\n")


class MemorySink(Sink):
    """In-memory sink for testing."""

    def __init__(self) -> None:
        self.events: list[ObservabilityEvent] = []

    def write(self, event: ObservabilityEvent) -> None:
        self.events.append(event)
