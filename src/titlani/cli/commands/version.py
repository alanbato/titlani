"""Version command."""

from rich.console import Console

from ...cli import display_version_info

console = Console()


def version() -> None:
    """Show version information."""
    display_version_info(console)
