"""Verification cache commands."""

from pathlib import Path

import typer
from rich.console import Console

from ...cli import display_verification_list

console = Console()

verification_app = typer.Typer(
    help="Manage sender verification cache",
    no_args_is_help=True,
)


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
