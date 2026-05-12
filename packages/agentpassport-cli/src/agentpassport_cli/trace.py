from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click
from agentpassport.identity.signing import _decode_jwt_claims, _verify_jwt_signature
from agentpassport.types import ObservabilityEvent
from nacl.exceptions import BadSignatureError
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------

@click.group()
def trace() -> None:
    """View and analyze task execution traces."""


@trace.command("show")
@click.option("--id", "trace_id", required=True, help="Trace ID to display")
@click.option(
    "--file", "log_file", type=click.Path(exists=True), help="Log file to read events from"
)
@click.option("--json-output", "json_out", is_flag=True, help="Output raw JSON")
def show(trace_id: str, log_file: str | None, json_out: bool) -> None:
    """Display a trace tree including auth chain for each task."""
    events = _load_events(log_file, trace_id)

    if not events:
        console.print(f"[red]No events found for trace {trace_id}[/red]")
        return

    if json_out:
        for evt in events:
            click.echo(evt.model_dump_json())
        return

    _render_trace(trace_id, events)


# ---------------------------------------------------------------------------
# Event loading
# ---------------------------------------------------------------------------

def _load_events(log_file: str | None, trace_id: str) -> list[ObservabilityEvent]:
    """Load events from a log file, filtering by trace_id."""
    if log_file is None:
        default_path = Path.home() / ".agentpassport" / "traces.jsonl"
        if not default_path.exists():
            return []
        log_file = str(default_path)

    events: list[ObservabilityEvent] = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = ObservabilityEvent.model_validate_json(line)
                if evt.trace_id == trace_id:
                    events.append(evt)
            except Exception:
                continue
    return events


# ---------------------------------------------------------------------------
# Auth chain rendering helpers
# ---------------------------------------------------------------------------

def _abbrev_did(did: str, width: int = 24) -> str:
    """Shorten a did:key:z... for display: keep scheme + first/last chars."""
    if len(did) <= width:
        return did
    # "did:key:z" is 9 chars; show 9 + first 8 of key + "…" + last 6
    prefix = did[:17]  # "did:key:z" + 8 key chars
    suffix = did[-6:]
    return f"{prefix}…{suffix}"


def _fmt_ts(unix_ts: float) -> str:
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_auth_chain(
    auth_chain: list[str],
    agent_did: str,
    parent: Tree,
) -> None:
    """Add an auth chain subtree to *parent*."""
    if not auth_chain:
        parent.add("[dim]auth chain: empty[/dim]")
        return

    chain_node = parent.add("[bold cyan]auth chain[/bold cyan]")

    for i, token in enumerate(auth_chain):
        hop_label = f"hop {i + 1}"

        try:
            claims = _decode_jwt_claims(token)
        except Exception as exc:
            chain_node.add(f"[red]{hop_label}: malformed token — {exc}[/red]")
            continue

        iss = claims.get("iss", "?")
        sub = claims.get("sub", "?")
        scope = claims.get("scope", [])
        exp_ts = claims.get("exp")
        jti = claims.get("jti", "?")

        # Signature verification — requires the public key embedded in the DID
        verified = _verify_hop(token, iss)
        status_mark = "[green]✓[/green]" if verified else "[red]✗[/red]"

        # Expiry check
        now_ts = datetime.now(timezone.utc).timestamp()
        if exp_ts is not None and now_ts > exp_ts:
            expiry_label = f"[red]expired {_fmt_ts(exp_ts)}[/red]"
        elif exp_ts is not None:
            expiry_label = f"[dim]exp {_fmt_ts(exp_ts)}[/dim]"
        else:
            expiry_label = "[dim]no expiry[/dim]"

        scope_str = ", ".join(scope) if scope else "[dim]none[/dim]"

        hop_node = chain_node.add(
            f"{status_mark} [bold]{hop_label}[/bold]  jti=[dim]{jti[:8]}…[/dim]"
        )
        hop_node.add(f"[dim]iss[/dim] {_abbrev_did(iss)}")
        hop_node.add(f"[dim]sub[/dim] {_abbrev_did(sub)}")
        hop_node.add(f"[dim]scope[/dim] {scope_str}")
        hop_node.add(expiry_label)


def _verify_hop(token: str, issuer_did: str) -> bool:
    """Verify a single JWT hop's signature using the public key embedded in the DID.

    Returns False (rather than raising) on any verification failure.
    """
    try:
        from agentpassport.identity.did import parse_did
        pub_key_bytes = parse_did(issuer_did)
        _verify_jwt_signature(token, pub_key_bytes)
        return True
    except (BadSignatureError, ValueError, Exception):
        return False


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def _render_trace(trace_id: str, events: list[ObservabilityEvent]) -> None:
    """Render events as a rich tree, with auth chain per task."""
    console.print()
    tree = Tree(f"[bold white]trace[/bold white] [bold yellow]{trace_id}[/bold yellow]")

    # Group events by task_id preserving first-seen order
    tasks: dict[str, list[ObservabilityEvent]] = {}
    for evt in events:
        tasks.setdefault(evt.task_id, []).append(evt)

    for task_id, task_events in tasks.items():
        last_event = task_events[-1]
        final_state = last_event.to_state or last_event.event
        is_ok = final_state in ("completed", "task_completed")
        status_color = "green" if is_ok else "red"

        task_node = tree.add(
            f"[{status_color}]{task_id}[/{status_color}]"
            f"  [dim]agent:[/dim] {_abbrev_did(last_event.agent)}"
            f"  [dim]→[/dim] [{status_color}]{final_state}[/{status_color}]"
        )

        # Events timeline
        for evt in task_events:
            cost_part = f"  [dim]cost={evt.cost_used:.4f}[/dim]" if evt.cost_used else ""
            task_node.add(f"[dim]{evt.event}[/dim]{cost_part}")

        # Auth chain — use the metadata from the last event that carries one,
        # or fall back to an empty indicator.
        auth_chain: list[str] = []
        for evt in task_events:
            chain = (evt.metadata or {}).get("auth_chain")
            if chain:
                auth_chain = chain
                break

        _render_auth_chain(auth_chain, last_event.agent, task_node)

    console.print(tree)
    console.print()
