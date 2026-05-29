"""Tests for concurrent revoke calls on SqliteRevocationRegistry."""
from __future__ import annotations

import concurrent.futures
import uuid

from agentpassport.revocation import SqliteRevocationRegistry


def test_concurrent_revoke(tmp_path):
    registry = SqliteRevocationRegistry(db_path=str(tmp_path / "revoc.db"))
    registry.initialize()

    jtis = [str(uuid.uuid4()) for _ in range(50)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(registry.revoke, jti) for jti in jtis]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    for jti in jtis:
        assert registry.is_revoked(jti), f"jti {jti} should be revoked"
