"""Mailing list management commands."""

import re
from pathlib import Path

import typer
from rich.console import Console

from ...cli.mailbox import resolve_mailbox_dir
from ...server.lists import (
    SUBSCRIBERS_FILE,
    is_mailing_list,
    load_subscribers,
)

console = Console()
error_console = Console(stderr=True, style="bold red")

list_app = typer.Typer(
    help="Manage mailing lists",
    no_args_is_help=True,
)


@list_app.command("create")
def list_create(
    listname: str = typer.Argument(
        ..., help="Mailing list name (alphanumeric, dots, dashes, underscores)"
    ),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
) -> None:
    """Create a new mailing list mailbox."""
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", listname):
        error_console.print(
            f"Invalid list name: {listname}\n"
            "Must contain only letters, digits, dots, dashes, "
            "and underscores."
        )
        raise typer.Exit(code=1)

    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    list_path = resolved_dir / listname

    if list_path.exists():
        error_console.print(f"Mailbox '{listname}' already exists")
        raise typer.Exit(code=1)

    try:
        list_path.mkdir(parents=True)
        subscribers_file = list_path / SUBSCRIBERS_FILE
        subscribers_file.write_text(
            "# Mailing list subscribers\n# One address per line (mailbox@hostname)\n"
        )
        console.print(f"[green]Created mailing list: {listname}[/]")
        console.print(
            f"[dim]Add subscribers with: titlani list add {listname} <address>[/]"
        )
    except OSError as e:
        error_console.print(f"Error creating list: {e}")
        raise typer.Exit(code=1) from e


@list_app.command("subscribers")
def list_subscribers(
    listname: str = typer.Argument(..., help="Mailing list name"),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
) -> None:
    """Show subscribers for a mailing list."""
    list_path = _resolve_list_path(listname, mailbox_dir)

    if not is_mailing_list(list_path):
        error_console.print(f"Not a mailing list: {listname}")
        raise typer.Exit(code=1)

    subscribers = load_subscribers(list_path)

    if not subscribers:
        console.print(f"[yellow]No subscribers in {listname}[/]")
        return

    console.print(f"[bold cyan]{listname}[/] subscribers ({len(subscribers)}):")
    for addr in sorted(subscribers):
        console.print(f"  {addr}")


@list_app.command("add")
def list_add(
    listname: str = typer.Argument(..., help="Mailing list name"),
    address: str = typer.Argument(..., help="Subscriber address (mailbox@hostname)"),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
) -> None:
    """Add a subscriber to a mailing list."""
    if "@" not in address:
        error_console.print(f"Invalid address format: {address}")
        raise typer.Exit(code=1)

    address = address.strip().lower()
    list_path = _resolve_list_path(listname, mailbox_dir)

    if not is_mailing_list(list_path):
        error_console.print(f"Not a mailing list: {listname}")
        raise typer.Exit(code=1)

    existing = set(load_subscribers(list_path))
    if address in existing:
        console.print(f"[yellow]{address} is already subscribed to {listname}[/]")
        return

    try:
        subscribers_file = list_path / SUBSCRIBERS_FILE
        with subscribers_file.open("a") as f:
            f.write(f"{address}\n")
        console.print(f"[green]Added {address} to {listname}[/]")
    except OSError as e:
        error_console.print(f"Error updating subscribers: {e}")
        raise typer.Exit(code=1) from e


@list_app.command("remove")
def list_remove(
    listname: str = typer.Argument(..., help="Mailing list name"),
    address: str = typer.Argument(..., help="Subscriber address to remove"),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
) -> None:
    """Remove a subscriber from a mailing list."""
    address = address.strip().lower()
    list_path = _resolve_list_path(listname, mailbox_dir)

    if not is_mailing_list(list_path):
        error_console.print(f"Not a mailing list: {listname}")
        raise typer.Exit(code=1)

    existing = set(load_subscribers(list_path))
    if address not in existing:
        console.print(f"[yellow]{address} is not subscribed to {listname}[/]")
        return

    subscribers_file = list_path / SUBSCRIBERS_FILE
    try:
        lines = subscribers_file.read_text().splitlines()
        new_lines = [line for line in lines if line.strip().lower() != address]
        subscribers_file.write_text("\n".join(new_lines) + "\n")
        console.print(f"[green]Removed {address} from {listname}[/]")
    except OSError as e:
        error_console.print(f"Error updating subscribers: {e}")
        raise typer.Exit(code=1) from e


def _resolve_list_path(listname: str, mailbox_dir: Path | None) -> Path:
    """Resolve to the list mailbox directory path."""
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    list_path = resolved_dir / listname
    if not list_path.is_dir():
        error_console.print(f"List not found: {listname}")
        raise typer.Exit(code=1)
    return list_path
