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
        create_mailbox_subdir(default, user)
    return default


def get_current_mailbox(error_console: Console) -> str:
    """Get the current user's mailbox name from $USER."""
    user = os.environ.get("USER")
    if not user:
        error_console.print("Cannot determine mailbox: $USER not set")
        raise SystemExit(1)
    return user


def verify_mailbox_access(mailbox_path: Path, error_console: Console) -> None:
    """Verify the current process owns the mailbox directory.

    Compares the directory's UID against ``os.getuid()``.  If the
    directory does not exist yet there is nothing to protect, so
    the check is skipped.
    """
    try:
        dir_uid = mailbox_path.stat().st_uid
    except FileNotFoundError:
        return  # Not yet created, nothing to protect
    except OSError as e:
        error_console.print(f"Error checking mailbox permissions: {e}")
        raise SystemExit(1) from e

    if dir_uid != os.getuid():
        error_console.print(
            f"Permission denied: mailbox '{mailbox_path.name}' is not owned by you"
        )
        raise SystemExit(1)


def create_mailbox_subdir(mailbox_dir: Path, mailbox: str) -> Path:
    """Create a mailbox subdirectory with 0o700 permissions."""
    path = mailbox_dir / mailbox
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError as e:
        raise OSError(f"Failed to create or secure mailbox '{path}': {e}") from e
    return path


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
                except (ValueError, OSError, UnicodeDecodeError) as e:
                    error_console.print(f"[yellow]Skipping {gemmail_file.name}: {e}[/]")

    return messages


def is_new_message(filepath: Path) -> bool:
    """Check if a message file has the .new unread marker."""
    return filepath.name.endswith(".new")


def _is_encrypted(filepath: Path) -> bool:
    """Check if a message file is encrypted (.gemmail.enc or .gemmail.enc.new)."""
    return ".enc" in filepath.suffixes
