from __future__ import annotations

import json
import os
from pathlib import Path

from agentpassport.identity.did import generate_keypair, did_from_public_key


class FileKeystore:
    """Simple file-based key storage for development."""

    def __init__(self, path: Path | None = None):
        self.path = path or Path.home() / ".agentpassport" / "keys.json"

    def generate_and_store(self, alias: str) -> str:
        """Generate a new keypair, store it, return the DID."""
        private_key, public_key = generate_keypair()
        did = did_from_public_key(public_key)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self._load()
        data[alias] = {
            "did": did,
            "private_key": private_key.hex(),
            "public_key": public_key.hex(),
        }
        serialized = json.dumps(data, indent=2)
        # Write with restricted permissions (owner read/write only)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(serialized)
        return did

    def get_private_key(self, alias: str) -> bytes:
        data = self._load()
        return bytes.fromhex(data[alias]["private_key"])

    def get_public_key(self, alias: str) -> bytes:
        data = self._load()
        return bytes.fromhex(data[alias]["public_key"])

    def get_did(self, alias: str) -> str:
        data = self._load()
        return data[alias]["did"]

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())
