from __future__ import annotations

import click

from agentpassport_cli.identity import identity
from agentpassport_cli.trace import trace


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """agentpassport CLI - Agent Protocol Stack tools."""


cli.add_command(trace)
cli.add_command(identity)
