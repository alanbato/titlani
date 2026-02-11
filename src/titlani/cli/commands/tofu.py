"""TOFU database commands."""

import typer
from rich.console import Console

from ...cli import confirm_action, display_tofu_list
from ...protocol.constants import DEFAULT_PORT

console = Console()

tofu_app = typer.Typer(
    help="Manage TOFU certificate database",
    no_args_is_help=True,
)


@tofu_app.command("list")
def tofu_list() -> None:
    """List all known hosts in TOFU database."""
    from tlacacoca import TOFUDatabase

    db = TOFUDatabase()
    hosts = db.list_hosts()
    display_tofu_list(hosts, console)


@tofu_app.command("revoke")
def tofu_revoke(
    tofu_hostname: str = typer.Argument(..., help="Hostname to revoke"),
    port: int | None = typer.Option(
        None,
        "--port",
        "-p",
        help=f"Port number (default: {DEFAULT_PORT})",
    ),
) -> None:
    """Remove a host from the TOFU database."""
    from tlacacoca import TOFUDatabase

    db = TOFUDatabase()
    effective_port = port if port is not None else DEFAULT_PORT

    if not confirm_action(
        f"Revoke certificate for [cyan]{tofu_hostname}:{effective_port}[/]?",
        console,
    ):
        console.print("[dim]Cancelled.[/]")
        return

    if db.revoke(tofu_hostname, effective_port):
        console.print(
            f"[green]Revoked certificate for {tofu_hostname}:{effective_port}[/]"
        )
    else:
        console.print(f"[yellow]Host {tofu_hostname}:{effective_port} not in database[/]")
