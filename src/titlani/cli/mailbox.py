"""Shared mailbox resolution and listing logic for mail commands."""

import os
from pathlib import Path

from rich.console import Console

from ..content.gemmail import GemmailMessage
from ..server.config import default_mailbox_dir
from .config import ClientConfig


def resolve_mailbox_dir(explicit: Path | None, error_console: Console) -> Path:
    """Resolve mailbox directory: explicit arg -> config file -> default."""
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

    default = default_mailbox_dir()
    default.mkdir(parents=True, exist_ok=True)
    user = os.environ.get("USER")
    if user:
        (default / user).mkdir(exist_ok=True)
    return default


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
        all_files: list[Path] = []
        for pattern in (
            "*.gemmail",
            "*.gemmail.new",
            "*.gemmail.enc",
            "*.gemmail.enc.new",
        ):
            all_files.extend(mbox_path.glob(pattern))
        all_files.sort(key=lambda p: p.name, reverse=True)

        for gemmail_file in all_files:
            if _is_encrypted(gemmail_file):
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


def is_new_message(filepath: Path) -> bool:
    """Check if a message file has the .new unread marker."""
    return filepath.name.endswith(".new")


def _is_encrypted(filepath: Path) -> bool:
    """Check if a message file is encrypted (.gemmail.enc or .gemmail.enc.new)."""
    return ".enc" in filepath.suffixes
