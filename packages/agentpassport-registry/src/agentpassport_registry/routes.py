from __future__ import annotations

from datetime import UTC, datetime

from agentpassport.identity.did import parse_did
from agentpassport.identity.signing import _verify_jwt_signature, verify_agent_card
from agentpassport.types import AgentCard
from fastapi import APIRouter, HTTPException, Request
from nacl.exceptions import BadSignatureError

from agentpassport_registry.limiter import limiter
from agentpassport_registry.query import QueryEngine
from agentpassport_registry.storage.base import Storage

PUBLISH_RATE = "10/minute"
QUERY_RATE = "60/minute"

router = APIRouter()
_storage: Storage | None = None
_query_engine = QueryEngine()


def set_storage(storage: Storage) -> None:
    global _storage
    _storage = storage


def get_storage() -> Storage:
    if _storage is None:
        raise RuntimeError("Storage not configured")
    return _storage


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/agents", status_code=201)
@limiter.limit(PUBLISH_RATE)
def publish_agent(request: Request, card: AgentCard) -> dict[str, str]:
    if card.signature is not None:
        try:
            public_key_bytes = parse_did(card.did)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid DID: {e}") from e
        if not verify_agent_card(card, public_key_bytes):
            raise HTTPException(status_code=422, detail="AgentCard signature verification failed")
    get_storage().register(card)
    return {"status": "registered", "did": card.did}


@router.get("/v1/agents/query")
@limiter.limit(QUERY_RATE)
def query_agents(
    request: Request,
    capability: str,
    max_cost: float | None = None,
    max_latency_ms: int | None = None,
) -> list[dict]:
    cards = get_storage().list_all()
    results = _query_engine.query(
        cards,
        capability=capability,
        max_cost_per_task=max_cost,
        max_latency_ms=max_latency_ms,
    )
    return [card.model_dump() for card in results]


@router.get("/v1/agents/{did:path}")
@limiter.limit(QUERY_RATE)
def get_agent(request: Request, did: str) -> dict:
    card = get_storage().get(did)
    if card is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return card.model_dump()


@router.delete("/v1/agents/{did:path}", status_code=204)
@limiter.limit("10/minute")
def delete_agent(request: Request, did: str) -> None:
    proof = request.headers.get("X-Delete-Proof")
    if not _verify_delete_proof(did, proof):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Delete-Proof header")
    get_storage().delete(did)


def _verify_delete_proof(did: str, proof_header: str | None) -> bool:
    if not proof_header:
        return False
    try:
        public_key_bytes = parse_did(did)
    except (ValueError, Exception):
        return False
    try:
        claims = _verify_jwt_signature(proof_header, public_key_bytes)
    except (BadSignatureError, ValueError):
        return False
    # validate claims
    if claims.get("sub") != did:
        return False
    if claims.get("action") != "delete":
        return False
    now_ts = datetime.now(UTC).timestamp()
    try:
        exp = float(claims["exp"])
    except (KeyError, TypeError, ValueError):
        return False
    return not now_ts > exp
