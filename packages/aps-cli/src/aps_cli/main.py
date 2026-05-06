from __future__ import annotations

import click

from aps_cli.identity import identity
from aps_cli.trace import trace


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """APS CLI - Agent Protocol Stack tools."""


cli.add_command(trace)
cli.add_command(identity)
