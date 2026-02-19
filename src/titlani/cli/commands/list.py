"""Mailing list management commands."""

import asyncio
import re
from pathlib import Path

import typer
from rich.console import Console

from ...cli.mailbox import resolve_mailbox_dir
from ...server.lists import (
    SUBSCRIBERS_FILE,
    SUBSCRIPTION_DB_FILE,
    add_subscriber,
    is_mailing_list,
    load_subscribers,
    remove_subscriber,
)
from ...server.subscription import SubscriptionTokenStore

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
        list_path.mkdir(mode=0o700, parents=True)
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

    confirmed = load_subscribers(list_path)

    # Load pending subscriptions
    resolved_dir = list_path.parent
    db_path = resolved_dir / SUBSCRIPTION_DB_FILE
    pending_addrs: set[str] = set()
    if db_path.exists():
        with SubscriptionTokenStore(db_path) as store:
            for addr, _token, _ts in store.list_pending(listname):
                pending_addrs.add(addr)

    if not confirmed and not pending_addrs:
        console.print(f"[yellow]No subscribers in {listname}[/]")
        return

    total = len(confirmed) + len(pending_addrs)
    console.print(f"[bold cyan]{listname}[/] subscribers ({total}):")
    for addr in sorted(confirmed):
        console.print(f"  {addr} [green]\\[confirmed][/]")
    for addr in sorted(pending_addrs):
        if addr not in set(confirmed):
            console.print(f"  {addr} [yellow]\\[pending][/]")


@list_app.command("add")
def list_add(
    listname: str = typer.Argument(..., help="Mailing list name"),
    address: str = typer.Argument(..., help="Subscriber address (mailbox@hostname)"),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
    hostname: str | None = typer.Option(
        None, "--hostname", "-H", help="Server hostname for sending"
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip verification, add directly"
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

    if no_verify:
        added = add_subscriber(list_path, address)
        if added:
            console.print(f"[green]Added {address} to {listname}[/]")
        else:
            console.print(f"[yellow]{address} is already subscribed to {listname}[/]")
        return

    # Verification flow: create pending token and send confirmation
    resolved_dir = list_path.parent
    db_path = resolved_dir / SUBSCRIPTION_DB_FILE
    with SubscriptionTokenStore(db_path) as store:
        token = store.create_token(listname, address)

    if hostname is None:
        hostname = _resolve_hostname()

    if hostname is None:
        error_console.print(
            "Cannot determine hostname. "
            "Use --hostname or configure server.hostname in config."
        )
        raise typer.Exit(code=1)

    try:
        asyncio.run(_send_verification(listname, list_path, hostname, address, token))
        console.print(f"[green]Verification sent to {address} (pending)[/]")
    except Exception as e:
        console.print(
            f"[yellow]Token created but could not send: {e}[/]\n[dim]Token: {token}[/]"
        )


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

    removed = remove_subscriber(list_path, address)

    # Also clean up any pending entry
    resolved_dir = list_path.parent
    db_path = resolved_dir / SUBSCRIPTION_DB_FILE
    if db_path.exists():
        with SubscriptionTokenStore(db_path) as store:
            store.remove_pending(listname, address)

    if removed:
        console.print(f"[green]Removed {address} from {listname}[/]")
    else:
        console.print(f"[yellow]{address} is not subscribed to {listname}[/]")


def _resolve_list_path(listname: str, mailbox_dir: Path | None) -> Path:
    """Resolve to the list mailbox directory path."""
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    list_path = resolved_dir / listname
    if not list_path.is_dir():
        error_console.print(f"List not found: {listname}")
        raise typer.Exit(code=1)
    return list_path


def _resolve_hostname() -> str | None:
    """Try to read hostname from server config."""
    try:
        from platformdirs import user_config_path

        from ...server.config import ServerConfig

        config_path = user_config_path("titlani") / "server.toml"
        config = ServerConfig.from_toml(config_path)
        return config.server.hostname
    except Exception:
        return None


async def _send_verification(
    listname: str,
    list_path: Path,
    hostname: str,
    address: str,
    token: str,
) -> None:
    """Send a verification token message to the address."""
    from ...client.session import MisfinClient
    from ...server.lists import get_or_create_list_identity

    cert_path, key_path = get_or_create_list_identity(list_path, listname, hostname)
    body = (
        f"# Confirm subscription to {listname}\n"
        f"\n"
        f"Reply with the following to confirm:\n"
        f"confirm {token}\n"
    )
    async with MisfinClient(
        timeout=10.0,
        client_cert=cert_path,
        client_key=key_path,
    ) as client:
        await client.send(to=address, body=body)
