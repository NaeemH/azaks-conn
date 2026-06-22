"""Typer CLI: `azaks-conn` (alias `aksc`).

Fetch AKS kubeconfig and merge into ~/.kube/config by alias
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from azaks_conn import __version__

app = typer.Typer(
    name="azaks-conn",
    help="Fetch AKS kubeconfig and merge into ~/.kube/config by alias",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
)
stdout = Console()
stderr = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        stdout.print(f"azaks-conn [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def _root(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Common options."""


# TODO: replace this placeholder with real subcommands.
#
# Convention from the rest of the series:
# - Each subcommand goes in its own @app.command()-decorated function below.
# - Catch your typed errors (subclasses of AzaksConnError) and exit 2.
# - Use `stdout`/`stderr` consoles above so error text goes to fd 2.
# - Locator options accept env-var fallback via `envvar=`:
#       SubOpt = Annotated[str, typer.Option("--subscription", "-s",
#                                            envvar="AZURE_SUBSCRIPTION_ID")]
@app.command("hello")
def cmd_hello(
    name: Annotated[str, typer.Option("--name", "-n", help="Who to greet.")] = "world",
) -> None:
    """Placeholder command. Delete when you add real subcommands."""
    stdout.print(f"hello, [bold]{name}[/bold] — from [cyan]azaks-conn[/cyan]")
