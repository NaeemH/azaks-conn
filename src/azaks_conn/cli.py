"""Typer CLI: `azaks-conn` (alias `aksc`).

Fetch AKS kubeconfig and merge into ~/.kube/config by alias.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from azaks_conn import __version__
from azaks_conn.aks import get_credentials
from azaks_conn.errors import AzaksConnError
from azaks_conn.kubeconfig import (
    default_alias_dir,
    default_kubeconfig,
    merge_into,
    rename_entries,
    write_atomic,
)

app = typer.Typer(
    name="azaks-conn",
    help="Fetch AKS kubeconfig and merge into ~/.kube/config by alias.",
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


# ----------------------------------------------------------------- connect ----
ClusterArg = Annotated[
    str,
    typer.Argument(help="AKS cluster name."),
]
AliasOpt = Annotated[
    str | None,
    typer.Option(
        "--alias",
        "-a",
        help="Local context/cluster/user name. Defaults to [bold]CLUSTER[/bold].",
    ),
]
AdminOpt = Annotated[
    bool,
    typer.Option(
        "--admin",
        help=(
            "Fetch cluster-admin credentials (bypasses AAD). "
            "[yellow]Treat the resulting kubeconfig as a high-privilege secret.[/yellow]"
        ),
    ),
]
OverwriteOpt = Annotated[
    bool,
    typer.Option(
        "--overwrite",
        help="Replace any existing entries for ALIAS in ~/.kube/config.",
    ),
]
ResourceGroupOpt = Annotated[
    str | None,
    typer.Option(
        "--resource-group",
        "-g",
        envvar="AZURE_RESOURCE_GROUP",
        help="Resource group of the cluster. Falls back to [bold]AZURE_RESOURCE_GROUP[/bold].",
    ),
]
SubscriptionOpt = Annotated[
    str | None,
    typer.Option(
        "--subscription",
        "-s",
        envvar="AZURE_SUBSCRIPTION_ID",
        help="Azure subscription id or name. Falls back to [bold]AZURE_SUBSCRIPTION_ID[/bold].",
    ),
]


@app.command("connect")
def cmd_connect(
    cluster: ClusterArg,
    alias: AliasOpt = None,
    admin: AdminOpt = False,
    overwrite: OverwriteOpt = False,
    resource_group: ResourceGroupOpt = None,
    subscription: SubscriptionOpt = None,
) -> None:
    """Fetch credentials for [bold]CLUSTER[/bold] and merge into ~/.kube/config.

    Writes a per-alias snapshot to [bold]~/.kube/azaks-conn/<alias>[/bold] (0600)
    and adds/replaces matching entries in the main kubeconfig, then switches
    [bold]current-context[/bold] to the alias.
    """
    alias_resolved = alias or cluster
    try:
        cfg = get_credentials(
            cluster,
            resource_group=resource_group,
            subscription=subscription,
            admin=admin,
        )
        rename_entries(cfg, alias_resolved)
        alias_path = default_alias_dir() / alias_resolved
        write_atomic(alias_path, cfg)
        added = merge_into(default_kubeconfig(), cfg, alias_resolved, overwrite=overwrite)
    except AzaksConnError as exc:
        stderr.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    verb = "added" if added else "replaced"
    stdout.print(
        f"[green]✓[/green] {verb} context [bold cyan]{alias_resolved}[/bold cyan] "
        f"in {default_kubeconfig()}"
    )
    stdout.print(f"  snapshot: [dim]{alias_path}[/dim]")
    if admin:
        stderr.print(
            "[yellow]warning:[/yellow] fetched cluster-admin credentials — "
            "guard this kubeconfig like a root key."
        )
