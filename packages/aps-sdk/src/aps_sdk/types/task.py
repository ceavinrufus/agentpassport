from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskState(str, Enum):
    CREATED = "created"
    DELEGATED = "delegated"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Intent(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class Constraints(BaseModel):
    budget_credits: float = Field(default=100.0)
    deadline_ms: int | None = None
    max_delegations: int = Field(default=10)
    allowed_capabilities: list[str] = Field(default_factory=list)
    denied_capabilities: list[str] = Field(default_factory=list)

    @field_validator("budget_credits")
    @classmethod
    def budget_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("budget_credits must be non-negative")
        return v


class FailurePolicy(BaseModel):
    retry: bool = True
    max_retries: int = 2
    fallback: str = "return_partial"


class TaskEnvelope(BaseModel):
    aps_version: str = "1.0"
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:16]}")
    parent_id: str | None = None
    intent: Intent
    constraints: Constraints = Field(default_factory=Constraints)
    auth_chain: list[dict[str, Any]] = Field(default_factory=list)
    result_schema: dict[str, Any] | None = None
    failure_policy: FailurePolicy = Field(default_factory=FailurePolicy)
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:16]}")
    transport: str = "http"
    state: TaskState = TaskState.CREATED
