"""Administrative commands for mailbox management."""

import os
import pwd
import stat
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ...cli.display import confirm_action
from ...cli.mailbox import resolve_mailbox_dir

console = Console()
error_console = Console(stderr=True, style="bold red")

admin_app = typer.Typer(
    help="Administrative mailbox operations",
    no_args_is_help=True,
)


@admin_app.command("fixperms")
def admin_fixperms(
    mailbox_dir: Path | None = typer.Option(
        None,
        "--mailbox-dir",
        "-d",
        help="Mailbox directory (auto-detected if omitted)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be changed without making changes",
    ),
) -> None:
    """Fix permissions on mailbox directories.

    Sets each mailbox subdirectory to mode 0o700.  Warns about
    ownership mismatches (fixing those requires root).
    """
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)

    subdirs = sorted(p for p in resolved_dir.iterdir() if p.is_dir())
    if not subdirs:
        console.print("[yellow]No mailbox subdirectories found[/]")
        return

    table = Table(title=f"Mailboxes in {resolved_dir}")
    table.add_column("Mailbox", style="cyan")
    table.add_column("Owner")
    table.add_column("Mode")
    table.add_column("Status")

    changes: list[Path] = []
    stat_errors = 0
    for subdir in subdirs:
        try:
            st = subdir.stat()
            mode = stat.S_IMODE(st.st_mode)
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
            except KeyError:
                owner = str(st.st_uid)

            problems: list[str] = []
            if mode != 0o700:
                problems.append(f"{oct(mode)} -> 0o700")
                changes.append(subdir)
            if owner != subdir.name:
                problems.append(f"owned by {owner}")

            status = ", ".join(problems) if problems else "[green]OK[/]"
            table.add_row(subdir.name, owner, oct(mode), status)
        except OSError as e:
            table.add_row(subdir.name, "?", "?", f"[red]{e}[/]")
            stat_errors += 1

    console.print(table)

    if stat_errors:
        error_console.print(f"\n{stat_errors} mailbox(es) could not be inspected")

    if not changes:
        if not stat_errors:
            console.print("\n[green]All mailbox permissions are correct[/]")
        return

    console.print(f"\n{len(changes)} mailbox(es) need permission fixes")

    if dry_run:
        console.print("[dim]Dry run — no changes made[/]")
        return

    if not confirm_action("Apply permission fixes?", console):
        console.print("[dim]Cancelled[/]")
        return

    fixed = 0
    failed = 0
    for path in changes:
        try:
            os.chmod(path, 0o700)
            fixed += 1
        except OSError as e:
            error_console.print(f"Error fixing {path.name}: {e}")
            failed += 1

    if failed:
        error_console.print(f"Fixed {fixed}, failed {failed} mailbox(es)")
        raise typer.Exit(code=1)
    console.print(f"[green]Fixed {fixed} mailbox(es)[/]")
