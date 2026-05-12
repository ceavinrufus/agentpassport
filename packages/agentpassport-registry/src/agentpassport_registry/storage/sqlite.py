from __future__ import annotations

import sqlite3

from agentpassport.types import AgentCard

from agentpassport_registry.storage.base import Storage


class SqliteStorage(Storage):
    def __init__(self, db_path: str = "agentpassport_registry.db") -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_cards (
                did TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._conn

    def register(self, card: AgentCard) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO agent_cards (did, data) VALUES (?, ?)",
            (card.did, card.model_dump_json()),
        )
        self.conn.commit()

    def get(self, did: str) -> AgentCard | None:
        row = self.conn.execute("SELECT data FROM agent_cards WHERE did = ?", (did,)).fetchone()
        if row is None:
            return None
        return AgentCard.model_validate_json(row[0])

    def delete(self, did: str) -> None:
        self.conn.execute("DELETE FROM agent_cards WHERE did = ?", (did,))
        self.conn.commit()

    def list_all(self) -> list[AgentCard]:
        rows = self.conn.execute("SELECT data FROM agent_cards").fetchall()
        return [AgentCard.model_validate_json(row[0]) for row in rows]
