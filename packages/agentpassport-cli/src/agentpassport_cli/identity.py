from __future__ import annotations

from pathlib import Path

import click
from agentpassport.identity.keystore import FileKeystore


@click.group()
def identity() -> None:
    """Manage agentpassport identities (DIDs and keys)."""


@identity.command("keygen")
@click.option("--alias", required=True, help="Alias for the keypair")
@click.option("--keystore", default=None, help="Path to keystore file")
def keygen(alias: str, keystore: str | None) -> None:
    """Generate a new Ed25519 keypair and DID."""
    path = Path(keystore) if keystore else None
    ks = FileKeystore(path=path)
    did = ks.generate_and_store(alias)
    click.echo(f"Generated DID: {did}")
    click.echo(f"Alias: {alias}")


@identity.command("list")
@click.option("--keystore", default=None, help="Path to keystore file")
def list_keys(keystore: str | None) -> None:
    """List all stored identities."""
    path = Path(keystore) if keystore else None
    ks = FileKeystore(path=path)
    data = ks._load()
    if not data:
        click.echo("No keys found.")
        return
    for alias, info in data.items():
        click.echo(f"  {alias}: {info['did']}")
