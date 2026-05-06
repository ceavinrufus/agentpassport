from __future__ import annotations

from abc import ABC, abstractmethod

from aps_sdk.types import AgentCard


class Storage(ABC):
    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def register(self, card: AgentCard) -> None: ...

    @abstractmethod
    def get(self, did: str) -> AgentCard | None: ...

    @abstractmethod
    def delete(self, did: str) -> None: ...

    @abstractmethod
    def list_all(self) -> list[AgentCard]: ...
