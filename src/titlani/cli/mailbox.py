"""Shared mailbox resolution and listing logic for mail commands."""

import os
from pathlib import Path

from rich.console import Console

from ..content.gemmail import GemmailMessage
from .config import ClientConfig


def resolve_mailbox_dir(explicit: Path | None, error_console: Console) -> Path:
    """Resolve mailbox directory: explicit arg -> config file -> error."""
    if explicit is not None:
        if not explicit.is_dir():
            error_console.print(f"Mailbox directory not found: {explicit}")
            raise SystemExit(1)
        return explicit

    config = ClientConfig.load()
    if config is not None:
        if not config.mailbox_dir.is_dir():
            error_console.print(f"Configured mailbox_dir not found: {config.mailbox_dir}")
            raise SystemExit(1)
        return config.mailbox_dir

    error_console.print(
        "No mailbox directory specified.\n"
        "Either pass it as an argument:\n"
        "  titlani mail list /var/mail/misfin\n"
        "Or set it in ~/.config/titlani/config.toml:\n"
        '  [mail]\n  mailbox_dir = "/var/mail/misfin"'
    )
    raise SystemExit(1)


def resolve_mailbox_name(explicit: str | None) -> str | None:
    """Resolve mailbox name: explicit arg -> $USER -> None."""
    if explicit is not None:
        return explicit
    return os.environ.get("USER")


def list_messages(
    mailbox_dir: Path,
    mailbox: str | None,
    error_console: Console,
) -> list[tuple[Path, GemmailMessage | None]]:
    """Scan mailbox directory and return (path, message) pairs.

    Ordering matches display_gemmail_list: newest first by filename.
    """
    messages: list[tuple[Path, GemmailMessage | None]] = []

    if mailbox:
        mbox_path = mailbox_dir / mailbox
        if not mbox_path.is_dir():
            error_console.print(f"Mailbox not found: {mailbox}")
            raise SystemExit(1)
        search_paths = [mbox_path]
    else:
        search_paths = sorted(p for p in mailbox_dir.iterdir() if p.is_dir())

    for mbox_path in search_paths:
        gemmail_files = sorted(mbox_path.glob("*.gemmail"), reverse=True)
        enc_files = sorted(mbox_path.glob("*.gemmail.enc"), reverse=True)
        all_files = sorted(
            [*gemmail_files, *enc_files],
            key=lambda p: p.name,
            reverse=True,
        )
        for gemmail_file in all_files:
            if gemmail_file.suffix == ".enc":
                messages.append((gemmail_file, None))
            else:
                try:
                    msg = GemmailMessage.from_bytes(gemmail_file.read_bytes())
                    messages.append((gemmail_file, msg))
                except ValueError:
                    error_console.print(
                        f"[yellow]Skipping invalid file: {gemmail_file.name}[/]"
                    )

    return messages
