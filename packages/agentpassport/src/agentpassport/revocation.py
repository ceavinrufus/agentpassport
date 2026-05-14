"""Soft revocation support for delegation JWTs.

Each delegation JWT carries a required `jti` (UUID) claim. When a
delegation should be stopped, the issuer revokes the jti. The
RevocationRegistry is checked inside verify_auth_chain() before a
task is allowed to execute — the agent completes its current atomic
action and stops before starting the next (soft stop).

Usage:
    registry = InMemoryRevocationRegistry()
    registry.revoke("some-jti-uuid")

    verify_auth_chain(
        auth_chain=[...],
        expected_subject=did,
        known_public_keys={...},
        revocation_registry=registry,
    )
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import UTC, datetime


class RevocationRegistry(ABC):
    """Abstract interface for JWT revocation storage."""

    @abstractmethod
    def revoke(self, jti: str) -> None:
        """Mark *jti* as revoked. Idempotent."""

    @abstractmethod
    def is_revoked(self, jti: str) -> bool:
        """Return True if *jti* has been revoked."""


class InMemoryRevocationRegistry(RevocationRegistry):
    """In-process revocation registry. State is lost on process restart."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    def revoke(self, jti: str) -> None:
        self._revoked.add(jti)

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked


class SqliteRevocationRegistry(RevocationRegistry):
    """Persistent revocation registry backed by a SQLite database.

    Call initialize() before first use.
    """

    def __init__(self, db_path: str = "agentpassport_revocation.db") -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create the database and table if they do not exist."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS revoked_jtis (
                jti TEXT PRIMARY KEY,
                revoked_at INTEGER NOT NULL
            )
        """)
        self._conn.commit()

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(
                "SqliteRevocationRegistry not initialized. Call initialize() first."
            )
        return self._conn

    def revoke(self, jti: str) -> None:
        """Mark *jti* as revoked. Idempotent — safe to call multiple times."""
        now_ts = int(datetime.now(UTC).timestamp())
        self._db.execute(
            "INSERT OR IGNORE INTO revoked_jtis (jti, revoked_at) VALUES (?, ?)",
            (jti, now_ts),
        )
        self._db.commit()

    def is_revoked(self, jti: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM revoked_jtis WHERE jti = ?", (jti,)
        ).fetchone()
        return row is not None
