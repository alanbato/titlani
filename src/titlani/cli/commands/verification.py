"""Verification cache commands."""

from pathlib import Path

import typer
from rich.console import Console

from ...cli import display_spki_list, display_verification_list
from ...cli.display import confirm_action

console = Console()

verification_app = typer.Typer(
    help="Manage sender verification cache",
    no_args_is_help=True,
)

spki_app = typer.Typer(
    help="Manage server SPKI cache",
    no_args_is_help=True,
)
verification_app.add_typer(spki_app, name="spki")


@verification_app.command("list")
def verification_list(
    cache_path: Path | None = typer.Option(
        None,
        "--cache",
        "-c",
        help="Path to verification cache database",
    ),
) -> None:
    """List all verified senders."""
    from ...verification.cache import SenderVerificationCache

    cache = SenderVerificationCache(cache_path)
    try:
        entries = cache.list_verified()
        display_verification_list(entries, console)
    finally:
        cache.close()


@spki_app.command("list")
def spki_list(
    cache_path: Path | None = typer.Option(
        None,
        "--cache",
        "-c",
        help="Path to verification cache database",
    ),
) -> None:
    """List all cached server SPKI hashes."""
    from ...verification.cache import SenderVerificationCache

    cache = SenderVerificationCache(cache_path)
    try:
        entries = cache.list_server_spki()
        display_spki_list(entries, console)
    finally:
        cache.close()


@spki_app.command("clear")
def spki_clear(
    cache_path: Path | None = typer.Option(
        None,
        "--cache",
        "-c",
        help="Path to verification cache database",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Clear all cached server SPKI hashes."""
    from ...verification.cache import SenderVerificationCache

    if not force:
        if not confirm_action("Clear all server SPKI cache entries?", console):
            console.print("[yellow]Cancelled.[/]")
            return

    cache = SenderVerificationCache(cache_path)
    try:
        count = cache.clear_server_spki()
        console.print(f"[green]Cleared {count} server SPKI entries.[/]")
    finally:
        cache.close()
