from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class ObservabilityEvent(BaseModel):
    trace_id: str
    task_id: str
    event: str
    from_state: str | None = None
    to_state: str | None = None
    agent: str  # did:key:z<base58btc>
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cost_used: float = 0.0
    budget_remaining: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
