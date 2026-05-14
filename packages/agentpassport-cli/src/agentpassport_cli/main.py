from __future__ import annotations

from importlib.metadata import version as pkg_version

import click

from agentpassport_cli.identity import identity
from agentpassport_cli.trace import trace


@click.group()
@click.version_option(version=pkg_version("agentpassport-cli"))
def cli() -> None:
    """agentpassport CLI - Agent Protocol Stack tools."""


cli.add_command(trace)
cli.add_command(identity)
