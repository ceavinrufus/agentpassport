"""Tests for concurrent register calls on SqliteStorage."""
from __future__ import annotations

import concurrent.futures

from agentpassport.identity.did import did_from_public_key, generate_keypair
from agentpassport.types import AgentCard
from agentpassport_registry.storage.sqlite import SqliteStorage


def _make_card(did: str) -> AgentCard:
    return AgentCard(
        did=did,
        name="Agent",
        capabilities=["test"],
        endpoint="http://agent:8000",
    )


def test_concurrent_register(tmp_path):
    storage = SqliteStorage(db_path=str(tmp_path / "test.db"))
    storage.initialize()

    keypairs = [generate_keypair() for _ in range(20)]
    dids = [did_from_public_key(pub) for _, pub in keypairs]
    cards = [_make_card(did) for did in dids]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(storage.register, card) for card in cards]
        for f in concurrent.futures.as_completed(futures):
            f.result()  # re-raise any exceptions

    all_cards = storage.list_all()
    stored_dids = {c.did for c in all_cards}
    assert stored_dids == set(dids)
