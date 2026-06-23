"""Typer CLI: `azaks-conn` (alias `aksc`).

Fetch AKS kubeconfig and merge into ~/.kube/config by alias.

Subcommands:
    connect   Fetch credentials, write alias snapshot, merge into ~/.kube/config.
    list      Show all aksc-managed aliases.
    verify    Probe a managed alias with `kubectl cluster-info`.
    rm        Remove an alias from state, snapshot, and ~/.kube/config.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from azaks_conn import __version__, config, kubectl
from azaks_conn.aks import get_credentials
from azaks_conn.config import AliasRecord, now_iso
from azaks_conn.errors import AzaksConnError, UnknownAliasError
from azaks_conn.kubeconfig import (
    default_alias_dir,
    default_kubeconfig,
    main_has_alias,
    merge_into,
    remove_from,
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


# --------------------------------------------------------------- option types ----
ClusterArg = Annotated[
    str,
    typer.Argument(help="AKS cluster name."),
]
AliasArg = Annotated[
    str,
    typer.Argument(help="Local alias previously registered via `aksc connect`."),
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
ForceOpt = Annotated[
    bool,
    typer.Option("--force", "-f", help="Skip the confirmation prompt."),
]
TimeoutOpt = Annotated[
    int,
    typer.Option(
        "--timeout",
        "-t",
        help="kubectl request timeout in seconds.",
        min=1,
        max=300,
    ),
]


# ----------------------------------------------------------------- connect ----
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

    Writes a per-alias snapshot to [bold]~/.kube/azaks-conn/<alias>[/bold] (0600),
    merges entries into the main kubeconfig, switches [bold]current-context[/bold]
    to the alias, and records metadata in the aksc state file.
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
        config.upsert(
            alias_resolved,
            AliasRecord(
                cluster=cluster,
                resource_group=resource_group,
                subscription=subscription,
                admin=admin,
                added_at=now_iso(),
            ),
        )
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
            "[bold yellow]warning:[/bold yellow] fetched [bold red]cluster-admin[/bold red] "
            "credentials — these bypass Entra ID / RBAC."
        )
        stderr.print(
            "  [dim]Treat this kubeconfig as a high-privilege secret. "
            "`aksc list` will flag it as ADMIN.[/dim]"
        )


# -------------------------------------------------------------------- list ----
@app.command("list")
def cmd_list() -> None:
    """List all aksc-managed kubeconfig aliases."""
    try:
        records = config.load()
    except AzaksConnError as exc:
        stderr.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if not records:
        stdout.print(
            "[dim]no aksc-managed aliases. "
            "Run [bold]aksc connect <cluster>[/bold] to add one.[/dim]"
        )
        return

    table = Table(title="aksc-managed aliases", show_lines=False)
    table.add_column("Alias", style="cyan", no_wrap=True)
    table.add_column("Cluster")
    table.add_column("Resource Group", style="dim")
    table.add_column("Subscription", style="dim")
    table.add_column("Admin", justify="center")
    table.add_column("Added")
    for alias_name, rec in sorted(records.items()):
        table.add_row(
            alias_name,
            rec.cluster,
            rec.resource_group or "-",
            rec.subscription or "-",
            "[bold red]ADMIN[/bold red]" if rec.admin else "-",
            rec.added_at or "-",
        )
    stdout.print(table)


# ------------------------------------------------------------------ verify ----
@app.command("verify")
def cmd_verify(
    alias: AliasArg,
    timeout: TimeoutOpt = 10,
) -> None:
    """Probe an aksc-managed [bold]ALIAS[/bold] using `kubectl cluster-info`."""
    try:
        records = config.load()
        if alias not in records:
            raise UnknownAliasError(
                f"no aksc-managed alias {alias!r}. Run `aksc list` to see what is registered."
            )
        out = kubectl.cluster_info(alias, timeout_seconds=timeout)
    except AzaksConnError as exc:
        stderr.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    stdout.print(f"[green]✓[/green] context [bold cyan]{alias}[/bold cyan] is reachable")
    first = next((ln for ln in out.splitlines() if ln.strip()), "")
    if first:
        stdout.print(f"  [dim]{first.strip()}[/dim]")
    if records[alias].admin:
        stderr.print(
            f"[bold yellow]warning:[/bold yellow] alias [bold cyan]{alias}[/bold cyan] "
            "holds [bold red]cluster-admin[/bold red] credentials — Entra ID / RBAC bypassed."
        )


# ---------------------------------------------------------------------- rm ----
@app.command("rm")
def cmd_rm(
    alias: AliasArg,
    force: ForceOpt = False,
) -> None:
    """Remove [bold]ALIAS[/bold] from state, snapshot, and ~/.kube/config."""
    try:
        records = config.load()
        snapshot_path = default_alias_dir() / alias
        main_path = default_kubeconfig()

        in_state = alias in records
        snapshot_exists = snapshot_path.exists()
        in_main = main_has_alias(main_path, alias)

        if not (in_state or snapshot_exists or in_main):
            stderr.print(
                f"[yellow]warning:[/yellow] no traces of alias "
                f"[bold cyan]{alias}[/bold cyan] found; nothing to do."
            )
            return

        if not force:
            typer.confirm(
                f"Remove alias {alias!r}? "
                f"(state={in_state}, snapshot={snapshot_exists}, kubeconfig={in_main})",
                abort=True,
            )

        removed_main = remove_from(main_path, alias)
        if snapshot_exists:
            snapshot_path.unlink(missing_ok=True)
        state_removed = config.remove(alias)
    except AzaksConnError as exc:
        stderr.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    stdout.print(f"[green]✓[/green] removed [bold cyan]{alias}[/bold cyan]")
    if removed_main:
        stdout.print(f"  - from {main_path}")
    if snapshot_exists:
        stdout.print(f"  - {snapshot_path}")
    if state_removed:
        stdout.print(f"  - from {config.state_file()}")
