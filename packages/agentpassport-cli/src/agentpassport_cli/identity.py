"""agentpassport CLI — identity management commands."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

import click
from agentpassport.identity.binding import (
    Binding,
    BindingDocument,
    bind_domain,
    bind_wallet,
    revoke_wallet,
    verify_domain_binding,
    verify_wallet_binding,
)
from agentpassport.identity.keystore import FileKeystore

# ---------------------------------------------------------------------------
# Domain validation helpers
# ---------------------------------------------------------------------------

_PORT_RE = re.compile(r":\d+$")
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _clean_domain(domain: str) -> str:
    """Strip scheme and path. Return cleaned domain or raise ValueError."""
    d = domain.strip()

    # Strip scheme
    for scheme in ("https://", "http://"):
        if d.lower().startswith(scheme):
            d = d[len(scheme):]

    # Strip path
    if "/" in d:
        d = d.split("/")[0]

    d = d.lower()

    # Reject port
    if _PORT_RE.search(d):
        raise ValueError(
            f"Domain should not include a port (got '{d}'). Use just the hostname."
        )

    # Reject bare IPs
    if _IP_RE.match(d):
        raise ValueError(
            f"'{d}' looks like an IP address. Use a domain name instead."
        )

    if not d:
        raise ValueError("Domain cannot be empty.")

    return d


# ---------------------------------------------------------------------------
# Keystore helpers
# ---------------------------------------------------------------------------

def _check_keystore_permissions(path: Path) -> None:
    """Warn if the keystore file is readable by group or others."""
    if not path.exists():
        return
    mode = path.stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        click.echo(
            f"⚠️  Warning: keystore file {path} is readable by others. "
            f"Run: chmod 600 {path}",
            err=True,
        )


def _load_keystore(ks: FileKeystore) -> None:
    """Check keystore permissions. Raises SystemExit on error."""
    _check_keystore_permissions(ks.path)


def _get_key(ks: FileKeystore, alias: str) -> tuple[bytes, str]:
    """Load private key + DID for alias. Clean error on failure."""
    try:
        raw = ks._load()
    except (json.JSONDecodeError, OSError) as e:
        click.echo(f"Error: could not read keystore: {e}", err=True)
        sys.exit(1)

    if alias not in raw:
        click.echo(
            f"Error: alias '{alias}' not found in keystore. "
            f"Run 'agentpass identity keygen --alias {alias}' first.",
            err=True,
        )
        sys.exit(1)

    try:
        priv = bytes.fromhex(raw[alias]["private_key"])
        did = raw[alias]["did"]
        if len(priv) < 32:
            raise ValueError("private key too short")
    except (KeyError, ValueError) as e:
        click.echo(
            f"Error: keystore entry for '{alias}' is corrupt: {e}. "
            f"Re-run keygen to regenerate.",
            err=True,
        )
        sys.exit(1)

    return priv[:32], did


# ---------------------------------------------------------------------------
# BindingDocument I/O helpers
# ---------------------------------------------------------------------------

CURRENT_BINDING_VERSION = "1"


def _load_binding_doc(output: str) -> BindingDocument:
    """Load existing BindingDocument, or create fresh. Validates version."""
    p = Path(output)

    if not p.exists():
        return BindingDocument(version=CURRENT_BINDING_VERSION)

    # Check it's not a directory
    if p.is_dir():
        click.echo(f"Error: '{output}' is a directory, not a file.", err=True)
        sys.exit(1)

    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as e:
        click.echo(
            f"Warning: could not parse existing '{output}' ({e}). Starting fresh.",
            err=True,
        )
        return BindingDocument(version=CURRENT_BINDING_VERSION)

    version = data.get("version")
    if version != CURRENT_BINDING_VERSION:
        click.echo(
            f"Error: '{output}' has unsupported version '{version}' "
            f"(expected '{CURRENT_BINDING_VERSION}'). Refusing to modify.",
            err=True,
        )
        sys.exit(1)

    try:
        return BindingDocument.from_dict(data)
    except (KeyError, TypeError) as e:
        click.echo(
            f"Warning: could not parse bindings in '{output}' ({e}). Starting fresh.",
            err=True,
        )
        return BindingDocument(version=CURRENT_BINDING_VERSION)


def _atomic_write(path: str, content: str) -> None:
    """Write content atomically (temp file + rename). Sets 0o644 permissions."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".ap-tmp-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.chmod(tmp, 0o644)
            os.replace(tmp, p)
        except Exception:
            os.unlink(tmp)
            raise
    except OSError as e:
        click.echo(f"Error: could not write '{path}': {e}", err=True)
        sys.exit(1)


def _has_duplicate(doc: BindingDocument, binding: Binding) -> bool:
    """Return True if an identical binding already exists."""
    for b in doc.bindings:
        if b.type == binding.type and b.claim == binding.claim and b.agent_did == binding.agent_did:
            return True
    return False


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------

@click.group()
def identity() -> None:
    """Manage agentpassport identities (DIDs and keys)."""


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------

@identity.command("keygen")
@click.option("--alias", required=True, help="Alias for the keypair")
@click.option("--keystore", default=None, help="Path to keystore file")
def keygen(alias: str, keystore: str | None) -> None:
    """Generate a new Ed25519 keypair and DID."""
    path = Path(keystore) if keystore else None
    ks = FileKeystore(path=path)
    did = ks.generate_and_store(alias)
    click.echo(f"✓ Generated DID: {did}")
    click.echo(f"  Alias: {alias}")
    click.echo(f"  Keystore: {ks.path}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@identity.command("list")
@click.option("--keystore", default=None, help="Path to keystore file")
def list_keys(keystore: str | None) -> None:
    """List all stored identities."""
    path = Path(keystore) if keystore else None
    ks = FileKeystore(path=path)
    _check_keystore_permissions(ks.path)
    try:
        data = ks._load()
    except (json.JSONDecodeError, OSError) as e:
        click.echo(f"Error: could not read keystore: {e}", err=True)
        sys.exit(1)
    if not data:
        click.echo("No keys found.")
        return
    for a, info in data.items():
        click.echo(f"  {a}: {info['did']}")


# ---------------------------------------------------------------------------
# bind-domain
# ---------------------------------------------------------------------------

@identity.command("bind-domain")
@click.option("--alias", required=True, help="Alias of the keypair to use")
@click.option("--domain", required=True, help="Domain to bind (e.g. rufus.dev)")
@click.option("--keystore", default=None, help="Path to keystore file")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Output file. Publish at https://{domain}/.well-known/agent-passport.json",
)
@click.option("--expires-at", default=None, type=int, help="Optional expiry as Unix timestamp")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def bind_domain_cmd(
    alias: str,
    domain: str,
    keystore: str | None,
    output: str,
    expires_at: int | None,
    yes: bool,
) -> None:
    """Create a signed domain ownership binding."""
    ks = FileKeystore(path=Path(keystore) if keystore else None)
    _load_keystore(ks)
    priv, did = _get_key(ks, alias)

    try:
        domain = _clean_domain(domain)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Validate expires_at
    if expires_at is not None:
        import time
        if expires_at <= int(time.time()):
            click.echo("Error: --expires-at is in the past.", err=True)
            sys.exit(1)

    # Confirmation
    click.echo(f"  DID:    {did}")
    click.echo(f"  Domain: {domain}")
    if expires_at:
        click.echo(f"  Expiry: {expires_at}")
    click.echo(f"  Output: {output}")
    click.echo()

    if not yes and not click.confirm("Create this domain binding?", default=False):
        click.echo("Aborted.")
        sys.exit(0)

    try:
        binding = bind_domain(priv, did, domain, expires_at=expires_at)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc = _load_binding_doc(output)

    if _has_duplicate(doc, binding):
        click.echo(f"ℹ️  A binding for '{domain}' already exists. Skipping.")
        sys.exit(0)

    doc.add(binding)
    _atomic_write(output, doc.to_json())

    click.echo(f"✓ Domain binding created for '{domain}'")
    click.echo()
    click.echo("  Publish the output file at:")
    click.echo(f"  https://{domain}/.well-known/agent-passport.json")


# ---------------------------------------------------------------------------
# bind-wallet
# ---------------------------------------------------------------------------

@identity.command("bind-wallet")
@click.option("--alias", required=True, help="Alias of the keypair to use")
@click.option("--chain", required=True, help="Chain (e.g. ethereum, solana, bitcoin)")
@click.option("--address", required=True, help="Wallet address")
@click.option("--keystore", default=None, help="Path to keystore file")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Output file. Publish at https://{domain}/.well-known/agent-passport.json",
)
@click.option("--expires-at", default=None, type=int, help="Optional expiry as Unix timestamp")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def bind_wallet_cmd(
    alias: str,
    chain: str,
    address: str,
    keystore: str | None,
    output: str,
    expires_at: int | None,
    yes: bool,
) -> None:
    """Create a signed wallet ownership binding."""
    ks = FileKeystore(path=Path(keystore) if keystore else None)
    _load_keystore(ks)
    priv, did = _get_key(ks, alias)

    # Validate expires_at
    if expires_at is not None:
        import time
        if expires_at <= int(time.time()):
            click.echo("Error: --expires-at is in the past.", err=True)
            sys.exit(1)

    # Validate address format early for clean error
    from agentpassport.identity.binding import validate_address
    try:
        validate_address(chain.lower(), address)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Confirmation — echo back details clearly so user can spot typos
    click.echo(f"  DID:     {did}")
    click.echo(f"  Chain:   {chain.lower()}")
    click.echo(f"  Address: {address}")
    if expires_at:
        click.echo(f"  Expiry:  {expires_at}")
    click.echo(f"  Output:  {output}")
    click.echo()
    click.echo("  ⚠️  Double-check the address — wallet bindings cannot be auto-corrected.")
    click.echo()

    if not yes and not click.confirm("Create this wallet binding?", default=False):
        click.echo("Aborted.")
        sys.exit(0)

    try:
        binding = bind_wallet(priv, did, chain, address, expires_at=expires_at)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc = _load_binding_doc(output)

    if _has_duplicate(doc, binding):
        click.echo(f"ℹ️  A binding for {chain}:{address} already exists. Skipping.")
        sys.exit(0)

    doc.add(binding)
    _atomic_write(output, doc.to_json())

    click.echo(f"✓ Wallet binding created for {chain}:{address}")


# ---------------------------------------------------------------------------
# revoke-wallet
# ---------------------------------------------------------------------------

@identity.command("revoke-wallet")
@click.option("--alias", required=True, help="Alias of the keypair to use")
@click.option("--chain", required=True, help="Chain identifier")
@click.option("--address", required=True, help="Wallet address to revoke")
@click.option("--keystore", default=None, help="Path to keystore file")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Binding document to update",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def revoke_wallet_cmd(
    alias: str,
    chain: str,
    address: str,
    keystore: str | None,
    output: str,
    yes: bool,
) -> None:
    """Revoke a wallet binding."""
    ks = FileKeystore(path=Path(keystore) if keystore else None)
    _load_keystore(ks)
    priv, did = _get_key(ks, alias)

    from agentpassport.identity.binding import validate_address
    try:
        validate_address(chain.lower(), address)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc = _load_binding_doc(output)

    # Cross-check: warn if no matching binding exists
    chain_lower = chain.lower()
    claim = {"chain": chain_lower, "address": address}
    matching_bindings = [
        b for b in doc.wallet_bindings()
        if b.agent_did == did and b.claim == claim
    ]
    if not matching_bindings:
        click.echo(
            f"⚠️  Warning: no matching wallet binding found for {chain_lower}:{address} "
            f"in '{output}'. A revocation will still be added.",
            err=True,
        )

    # Warn if already revoked
    already_revoked = any(
        r.agent_did == did and r.claim == claim
        for r in doc.revocations
    )
    if already_revoked:
        click.echo(
            f"ℹ️  A revocation for {chain_lower}:{address} already exists. Skipping.",
        )
        sys.exit(0)

    # Confirmation
    click.echo(f"  DID:     {did}")
    click.echo(f"  Chain:   {chain_lower}")
    click.echo(f"  Address: {address}")
    click.echo(f"  Output:  {output}")
    click.echo()

    if not yes and not click.confirm(
        "⚠️  Revoke this wallet binding? This cannot be undone without re-binding.",
        default=False,
    ):
        click.echo("Aborted.")
        sys.exit(0)

    try:
        revocation = revoke_wallet(priv, did, chain, address)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    doc.revoke(revocation)
    _atomic_write(output, doc.to_json())

    click.echo(f"✓ Wallet binding revoked for {chain_lower}:{address}")
    click.echo()
    click.echo("  Republish the updated file to take effect.")


# ---------------------------------------------------------------------------
# remove-binding
# ---------------------------------------------------------------------------

@identity.command("remove-binding")
@click.option(
    "--type", "binding_type",
    required=True,
    type=click.Choice(["domain", "wallet"]),
    help="Binding type to remove",
)
@click.option("--domain", default=None, help="Domain (for type=domain)")
@click.option("--chain", default=None, help="Chain (for type=wallet)")
@click.option("--address", default=None, help="Address (for type=wallet)")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Binding document to modify",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def remove_binding_cmd(
    binding_type: str,
    domain: str | None,
    chain: str | None,
    address: str | None,
    output: str,
    yes: bool,
) -> None:
    """Remove a specific binding from the document.

    Use this to fix typos or remove stale bindings.
    """
    # Validate args
    if binding_type == "domain":
        if not domain:
            click.echo("Error: --domain is required for type=domain.", err=True)
            sys.exit(1)
        try:
            domain = _clean_domain(domain)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        claim = {"domain": domain}
    else:
        if not chain or not address:
            click.echo("Error: --chain and --address are required for type=wallet.", err=True)
            sys.exit(1)
        claim = {"chain": chain.lower(), "address": address}

    doc = _load_binding_doc(output)

    # Find matching bindings
    matches = [
        b for b in doc.bindings
        if b.type == binding_type and b.claim == claim
    ]

    if not matches:
        click.echo(f"ℹ️  No matching '{binding_type}' binding found. Nothing to remove.")
        sys.exit(0)

    click.echo(f"  Found {len(matches)} matching binding(s):")
    for b in matches:
        click.echo(f"    - type={b.type}, claim={b.claim}, issued_at={b.issued_at}")
    click.echo()

    if not yes and not click.confirm("Remove these bindings?", default=False):
        click.echo("Aborted.")
        sys.exit(0)

    doc.bindings = [
        b for b in doc.bindings
        if not (b.type == binding_type and b.claim == claim)
    ]
    _atomic_write(output, doc.to_json())

    click.echo(f"✓ Removed {len(matches)} binding(s) from '{output}'")


# ---------------------------------------------------------------------------
# list-bindings
# ---------------------------------------------------------------------------

@identity.command("list-bindings")
@click.option(
    "--output",
    default="agent-passport.json",
    show_default=True,
    help="Binding document to inspect",
)
def list_bindings_cmd(output: str) -> None:
    """List all bindings and revocations in a document."""
    doc = _load_binding_doc(output)

    if not doc.bindings and not doc.revocations:
        click.echo("No bindings found.")
        return

    if doc.bindings:
        click.echo(f"Bindings ({len(doc.bindings)}):")
        for b in doc.bindings:
            revoked = doc.is_revoked(b)
            status = " [REVOKED]" if revoked else ""
            expired = " [EXPIRED]" if b.is_expired() else ""
            click.echo(f"  [{b.type}]{status}{expired}")
            click.echo(f"    did:     {b.agent_did}")
            click.echo(f"    claim:   {b.claim}")
            click.echo(f"    issued:  {b.issued_at}")
            if b.expires_at:
                click.echo(f"    expires: {b.expires_at}")

    if doc.revocations:
        click.echo()
        click.echo(f"Revocations ({len(doc.revocations)}):")
        for r in doc.revocations:
            click.echo(f"  [{r.type}]")
            click.echo(f"    did:     {r.agent_did}")
            click.echo(f"    claim:   {r.claim}")
            click.echo(f"    revoked: {r.revoked_at}")


# ---------------------------------------------------------------------------
# verify-domain
# ---------------------------------------------------------------------------

@identity.command("verify-domain")
@click.option("--did", required=True, help="Agent DID to verify")
@click.option("--domain", required=True, help="Domain to check")
@click.option("--timeout", default=5.0, show_default=True, help="HTTP timeout in seconds")
def verify_domain_cmd(did: str, domain: str, timeout: float) -> None:
    """Verify that a domain claims ownership of an agent DID.

    Fetches https://{domain}/.well-known/agent-passport.json and verifies.
    """
    try:
        domain = _clean_domain(domain)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"  Checking https://{domain}/.well-known/agent-passport.json ...")

    try:
        result = verify_domain_binding(did, domain, timeout=timeout)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result:
        click.echo(f"✓ Valid domain binding: '{domain}' claims {did}")
    else:
        click.echo(f"✗ No valid domain binding found for '{domain}' → {did}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# verify-wallet
# ---------------------------------------------------------------------------

@identity.command("verify-wallet")
@click.option("--did", required=True, help="Agent DID to verify")
@click.option("--chain", required=True, help="Chain identifier")
@click.option("--address", required=True, help="Wallet address")
@click.option("--domain", required=True, help="Domain hosting the binding document")
@click.option("--timeout", default=5.0, show_default=True, help="HTTP timeout in seconds")
def verify_wallet_cmd(did: str, chain: str, address: str, domain: str, timeout: float) -> None:
    """Verify that a wallet address is bound to an agent DID.

    Fetches https://{domain}/.well-known/agent-passport.json and verifies.
    """
    try:
        domain = _clean_domain(domain)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"  Checking https://{domain}/.well-known/agent-passport.json ...")

    try:
        result = verify_wallet_binding(did, chain, address, domain, timeout=timeout)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result:
        click.echo(f"✓ Valid wallet binding: {chain}:{address} → {did}")
    else:
        click.echo(f"✗ No valid wallet binding found for {chain}:{address} → {did}")
        sys.exit(1)
