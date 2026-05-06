from __future__ import annotations

from pathlib import Path

import click
from aps_sdk.types import ObservabilityEvent
from rich.console import Console
from rich.tree import Tree

console = Console()


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
    """Display a trace tree."""
    events = _load_events(log_file, trace_id)

    if not events:
        console.print(f"[red]No events found for trace {trace_id}[/red]")
        return

    if json_out:
        for evt in events:
            click.echo(evt.model_dump_json())
        return

    _render_tree(trace_id, events)


def _load_events(log_file: str | None, trace_id: str) -> list[ObservabilityEvent]:
    """Load events from a log file, filtering by trace_id."""
    if log_file is None:
        default_path = Path.home() / ".aps" / "traces.jsonl"
        if not default_path.exists():
            return []
        log_file = str(default_path)

    events = []
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


def _render_tree(trace_id: str, events: list[ObservabilityEvent]) -> None:
    """Render events as a rich tree."""
    tree = Tree(f"[bold]{trace_id}[/bold]")

    tasks: dict[str, list[ObservabilityEvent]] = {}
    for evt in events:
        tasks.setdefault(evt.task_id, []).append(evt)

    for task_id, task_events in tasks.items():
        last_event = task_events[-1]
        status_color = "green" if last_event.to_state == "completed" else "red"
        label = f"[{status_color}]{task_id}[/{status_color}] ({last_event.event})"
        tree.add(label)

    console.print(tree)
