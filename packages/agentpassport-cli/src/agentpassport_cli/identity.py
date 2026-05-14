from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from agentpassport.identity.binding import (
    BindingDocument,
    bind_domain,
    bind_wallet,
    revoke_wallet,
)
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


# ---------------------------------------------------------------------------
# Binding commands
# ---------------------------------------------------------------------------

def _load_binding_doc(output: str) -> BindingDocument:
    """Load existing BindingDocument from file, or create a new one."""
    p = Path(output)
    if p.exists():
        try:
            return BindingDocument.from_dict(json.loads(p.read_text()))
        except (json.JSONDecodeError, KeyError):
            click.echo(f"Warning: could not parse existing {output}, starting fresh.", err=True)
    return BindingDocument(version="1")


def _save_binding_doc(doc: BindingDocument, output: str) -> None:
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.to_json())


@identity.command("bind-domain")
@click.option("--alias", required=True, help="Alias of the keypair to use")
@click.option("--domain", required=True, help="Domain to bind (e.g. rufus.dev)")
@click.option("--keystore", default=None, help="Path to keystore file")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Output file path. Publish this at https://{domain}/.well-known/agent-passport.json",
)
@click.option("--expires-at", default=None, type=int, help="Optional expiry as Unix timestamp")
def bind_domain_cmd(
    alias: str,
    domain: str,
    keystore: str | None,
    output: str,
    expires_at: int | None,
) -> None:
    """Create a signed domain ownership binding and write it to a file.

    After running this command, publish the output file at:

        https://{domain}/.well-known/agent-passport.json

    Anyone can then verify your agent owns this domain with:

        agentpass identity verify-domain --did <DID> --domain <domain>
    """
    ks = FileKeystore(path=Path(keystore) if keystore else None)

    try:
        priv = ks.get_private_key(alias)
        did = ks.get_did(alias)
    except KeyError:
        click.echo(f"Error: alias '{alias}' not found in keystore. Run 'keygen' first.", err=True)
        sys.exit(1)

    try:
        binding = bind_domain(priv[:32], did, domain, expires_at=expires_at)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc = _load_binding_doc(output)
    doc.add(binding)
    _save_binding_doc(doc, output)

    click.echo(f"✓ Domain binding created for '{domain}'")
    click.echo(f"  DID:    {did}")
    click.echo(f"  Output: {output}")
    click.echo()
    click.echo("  Publish this file at:")
    click.echo(f"  https://{domain}/.well-known/agent-passport.json")


@identity.command("bind-wallet")
@click.option("--alias", required=True, help="Alias of the keypair to use")
@click.option("--chain", required=True, help="Chain identifier (e.g. ethereum, solana, bitcoin)")
@click.option("--address", required=True, help="Wallet address on the given chain")
@click.option("--keystore", default=None, help="Path to keystore file")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Output file path. Publish this at https://{domain}/.well-known/agent-passport.json",
)
@click.option("--expires-at", default=None, type=int, help="Optional expiry as Unix timestamp")
def bind_wallet_cmd(
    alias: str,
    chain: str,
    address: str,
    keystore: str | None,
    output: str,
    expires_at: int | None,
) -> None:
    """Create a signed wallet ownership binding and write it to a file.

    After running this command, publish the output file at:

        https://{domain}/.well-known/agent-passport.json
    """
    ks = FileKeystore(path=Path(keystore) if keystore else None)

    try:
        priv = ks.get_private_key(alias)
        did = ks.get_did(alias)
    except KeyError:
        click.echo(f"Error: alias '{alias}' not found in keystore. Run 'keygen' first.", err=True)
        sys.exit(1)

    try:
        binding = bind_wallet(priv[:32], did, chain, address, expires_at=expires_at)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc = _load_binding_doc(output)
    doc.add(binding)
    _save_binding_doc(doc, output)

    click.echo(f"✓ Wallet binding created for {chain}:{address}")
    click.echo(f"  DID:    {did}")
    click.echo(f"  Output: {output}")


@identity.command("revoke-wallet")
@click.option("--alias", required=True, help="Alias of the keypair to use")
@click.option("--chain", required=True, help="Chain identifier")
@click.option("--address", required=True, help="Wallet address to revoke")
@click.option("--keystore", default=None, help="Path to keystore file")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Output file to update with revocation",
)
def revoke_wallet_cmd(
    alias: str,
    chain: str,
    address: str,
    keystore: str | None,
    output: str,
) -> None:
    """Revoke a wallet binding. Updates the binding document with a revocation entry."""
    ks = FileKeystore(path=Path(keystore) if keystore else None)

    try:
        priv = ks.get_private_key(alias)
        did = ks.get_did(alias)
    except KeyError:
        click.echo(f"Error: alias '{alias}' not found in keystore.", err=True)
        sys.exit(1)

    try:
        revocation = revoke_wallet(priv[:32], did, chain, address)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc = _load_binding_doc(output)
    doc.revoke(revocation)
    _save_binding_doc(doc, output)

    click.echo(f"✓ Wallet binding revoked for {chain}:{address}")
    click.echo(f"  Output: {output}")
    click.echo()
    click.echo("  Republish the updated file to take effect.")
