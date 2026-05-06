from __future__ import annotations
from pydantic import BaseModel, Field


class CostInfo(BaseModel):
    currency: str = "credits"
    per_task: float = 0.0


class AgentCard(BaseModel):
    did: str
    name: str
    version: str = "0.1.0"
    capabilities: list[str]
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    cost: CostInfo = Field(default_factory=CostInfo)
    latency_p99_ms: int | None = None
    trust_requirements: list[str] = Field(default_factory=list)
    transports: list[str] = Field(default_factory=lambda: ["http"])
    endpoint: str
