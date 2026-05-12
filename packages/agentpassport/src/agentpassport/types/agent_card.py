from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


class CostInfo(BaseModel):
    currency: str = "credits"
    per_task: float = 0.0


class AgentCard(BaseModel):
    did: str
    name: str
    version: str = "0.1.0"
    capabilities: list[str]
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    cost: CostInfo = Field(default_factory=CostInfo)
    latency_p99_ms: int | None = None
    trust_requirements: list[str] = Field(default_factory=list)
    transports: list[str] = Field(default_factory=lambda: ["http"])
    endpoint: str
    signature: str | None = None  # hex-encoded Ed25519 sig over canonical_payload()

    def canonical_payload(self) -> bytes:
        """Deterministic bytes for signing and verification.

        Signed fields: name, did, capabilities (sorted), endpoint.
        Mutable metadata (version, cost, latency, schemas, transports,
        trust_requirements) and the signature field itself are excluded.

        Uses sorted keys and compact JSON separators for determinism.
        """
        payload = {
            "capabilities": sorted(self.capabilities),
            "did": self.did,
            "endpoint": self.endpoint,
            "name": self.name,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).digest()
