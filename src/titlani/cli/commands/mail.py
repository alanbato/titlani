"""Mail commands: list, search, read, delete, reply."""

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

import typer
from rich.console import Console

from ...cli import (
    confirm_action,
    display_gemmail_list,
    display_gemmail_message,
    format_status_response,
)
from ...cli._helpers import (
    build_sender_from_cert,
    read_encrypted_message,
    validate_cert_key_pair,
)
from ...cli.mailbox import (
    get_current_mailbox,
    is_new_message,
    list_messages,
    resolve_mailbox_dir,
    verify_mailbox_access,
)
from ...client.session import MisfinClient
from ...content.gemmail import GemmailMessage
from ...content.message_id import (
    build_reply_link,
    parse_message_id_from_filename,
)
from ...protocol.status import is_success

console = Console()
error_console = Console(stderr=True, style="bold red")

mail_app = typer.Typer(
    help="Read stored mail",
    no_args_is_help=True,
)


@mail_app.command("list")
def mail_list(
    mailbox_dir: Path | None = typer.Argument(
        None,
        help="Path to mailbox directory (auto-detected from config if omitted)",
    ),
) -> None:
    """List messages in your mailbox."""
    mailbox = get_current_mailbox(error_console)
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    verify_mailbox_access(resolved_dir / mailbox, error_console)
    messages = list_messages(resolved_dir, mailbox, error_console)
    display_gemmail_list(messages, console)


@mail_app.command("search")
def mail_search(
    query: str | None = typer.Argument(
        None,
        help="Text to search for across all fields (sender, subject, body)",
    ),
    from_filter: str | None = typer.Option(
        None,
        "--from",
        "-f",
        help="Filter by sender address or name",
    ),
    subject_filter: str | None = typer.Option(
        None,
        "--subject",
        "-s",
        help="Filter by subject text",
    ),
    body_filter: str | None = typer.Option(
        None,
        "--body",
        "-b",
        help="Filter by body text",
    ),
    mailbox_dir: Path | None = typer.Option(
        None,
        "--mailbox-dir",
        "-d",
        help="Mailbox directory",
    ),
    encryption_key: Path | None = typer.Option(
        None,
        "--encryption-key",
        "-e",
        help="Path to X25519 private key for decrypting .enc messages",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Search messages by sender, subject, or body text."""
    if not query and not from_filter and not subject_filter and not body_filter:
        error_console.print(
            "Provide a search query or at least one filter "
            "(--from, --subject, --body)"
        )
        raise typer.Exit(code=1)

    mailbox = get_current_mailbox(error_console)
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    verify_mailbox_access(resolved_dir / mailbox, error_console)
    messages = list_messages(resolved_dir, mailbox, error_console)

    matches: list[tuple[Path, GemmailMessage | None]] = []
    encrypted_skipped = 0

    for filepath, msg in messages:
        if msg is None:
            # Encrypted — try decrypting if key provided
            if encryption_key:
                try:
                    msg = read_encrypted_message(
                        filepath, encryption_key, error_console
                    )
                except (typer.Exit, Exception):
                    encrypted_skipped += 1
                    continue
            else:
                encrypted_skipped += 1
                continue

        if _message_matches(msg, query, from_filter, subject_filter, body_filter):
            matches.append((filepath, msg))

    display_gemmail_list(matches, console)
    if encrypted_skipped:
        console.print(
            f"[dim]({encrypted_skipped} encrypted message(s) skipped)[/]"
        )


def _message_matches(
    msg: GemmailMessage,
    query: str | None,
    from_filter: str | None,
    subject_filter: str | None,
    body_filter: str | None,
) -> bool:
    """Check if a message matches the search criteria (AND logic)."""
    if query:
        q = query.lower()
        sender_text = " ".join(s.long_form for s in msg.senders).lower()
        subject_text = (msg.subject or "").lower()
        body_text = msg.body.lower()
        if q not in sender_text and q not in subject_text and q not in body_text:
            return False

    if from_filter:
        f = from_filter.lower()
        sender_text = " ".join(s.long_form for s in msg.senders).lower()
        if f not in sender_text:
            return False

    if subject_filter:
        s = subject_filter.lower()
        if s not in (msg.subject or "").lower():
            return False

    if body_filter:
        b = body_filter.lower()
        if b not in msg.body.lower():
            return False

    return True


@mail_app.command("read")
def mail_read(
    message: str = typer.Argument(
        ...,
        help="Message index (from 'mail list') or path to .gemmail file",
    ),
    mailbox_dir: Path | None = typer.Option(
        None,
        "--mailbox-dir",
        "-d",
        help="Mailbox directory",
    ),
    encryption_key: Path | None = typer.Option(
        None,
        "--encryption-key",
        "-e",
        help="Path to X25519 private key for decryption",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Read and display a gemmail message."""
    gemmail_file = _resolve_message_path(message, mailbox_dir)

    try:
        if ".enc" in gemmail_file.suffixes:
            msg = read_encrypted_message(
                gemmail_file, encryption_key, error_console
            )
        else:
            msg = GemmailMessage.from_bytes(gemmail_file.read_bytes())
        display_gemmail_message(msg, console)

        # Mark as read by removing .new suffix
        if is_new_message(gemmail_file):
            read_name = gemmail_file.name.removesuffix(".new")
            try:
                gemmail_file.rename(gemmail_file.parent / read_name)
            except OSError as e:
                error_console.print(
                    f"[yellow]Warning: could not mark as read: "
                    f"{e}[/]"
                )
    except ValueError as e:
        error_console.print(f"Invalid gemmail format: {e}")
        raise typer.Exit(code=1) from e
    except typer.Exit:
        raise
    except (OSError, UnicodeDecodeError) as e:
        error_console.print(f"Error reading message: {e}")
        raise typer.Exit(code=1) from e


@mail_app.command("delete")
def mail_delete(
    messages: list[str] = typer.Argument(
        ...,
        help="Message indices (from 'mail list') or paths to .gemmail files",
    ),
    mailbox_dir: Path | None = typer.Option(
        None,
        "--mailbox-dir",
        "-d",
        help="Mailbox directory",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete one or more stored messages."""
    resolved_files: list[Path] = []
    cached_messages = None
    for msg in messages:
        try:
            index = int(msg)
        except ValueError:
            index = None

        if index is not None:
            if cached_messages is None:
                resolved_mailbox = get_current_mailbox(error_console)
                resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
                verify_mailbox_access(
                    resolved_dir / resolved_mailbox, error_console
                )
                cached_messages = list_messages(
                    resolved_dir, resolved_mailbox, error_console
                )
            if index < 1 or index > len(cached_messages):
                error_console.print(
                    f"Invalid message index: {index} "
                    f"(valid range: 1-{len(cached_messages)})"
                )
                raise typer.Exit(code=1)
            resolved_files.append(cached_messages[index - 1][0])
        else:
            filepath = Path(msg).resolve()
            if not filepath.exists():
                error_console.print(f"File not found: {filepath}")
                raise typer.Exit(code=1)
            resolved_files.append(filepath)

    if not force:
        file_list = "\n".join(f"  {f.name}" for f in resolved_files)
        if not confirm_action(
            f"Delete {len(resolved_files)} message(s)?\n{file_list}",
            console,
        ):
            console.print("[dim]Cancelled.[/]")
            return

    deleted = 0
    failed = 0
    for filepath in resolved_files:
        try:
            filepath.unlink()
            deleted += 1
        except OSError as e:
            error_console.print(f"Error deleting {filepath.name}: {e}")
            failed += 1

    if failed:
        error_console.print(
            f"Deleted {deleted}, failed {failed} message(s)"
        )
        raise typer.Exit(code=1)
    console.print(f"[green]Deleted {deleted} message(s).[/]")


@mail_app.command("reply")
def mail_reply(
    gemmail_file: Path = typer.Argument(
        ...,
        help="Path to .gemmail or .gemmail.enc file to reply to",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    reply_message: str | None = typer.Option(
        None,
        "--message",
        "-m",
        help="Reply message body",
    ),
    quote: bool = typer.Option(
        False,
        "--quote",
        "-q",
        help="Quote the original message with > prefix",
    ),
    cert: Path | None = typer.Option(
        None,
        "--cert",
        help="Path to sender identity certificate",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    key: Path | None = typer.Option(
        None,
        "--key",
        help="Path to sender identity private key",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    encryption_key: Path | None = typer.Option(
        None,
        "--encryption-key",
        "-e",
        help="Path to X25519 private key for decryption",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", "-t", help="Request timeout in seconds"
    ),
) -> None:
    """Reply to a gemmail message."""
    validate_cert_key_pair(cert, key, error_console)

    # Read original message
    try:
        if ".enc" in gemmail_file.suffixes:
            original = read_encrypted_message(gemmail_file, encryption_key, error_console)
        else:
            original = GemmailMessage.from_bytes(gemmail_file.read_bytes())
    except typer.Exit:
        raise
    except Exception as e:
        error_console.print(f"Error reading message: {e}")
        raise typer.Exit(code=1) from e

    # Extract reply-to address
    if not original.senders:
        error_console.print("Cannot reply: message has no sender address")
        raise typer.Exit(code=1)

    reply_to = original.senders[0]

    # Determine subject
    original_subject = original.subject or ""
    if original_subject.startswith("Re: "):
        reply_subject = original_subject
    elif original_subject:
        reply_subject = f"Re: {original_subject}"
    else:
        reply_subject = None

    # Get reply body
    if reply_message is None:
        editor = os.environ.get("EDITOR", "vi")
        initial_content = ""
        if quote:
            quoted = "\n".join(f"> {line}" for line in original.body.split("\n"))
            initial_content = f"\n\n{quoted}"

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as tf:
            tf.write(initial_content)
            tf_path = tf.name

        try:
            subprocess.run([editor, tf_path], check=True)
            reply_body = Path(tf_path).read_text()
        except subprocess.CalledProcessError as e:
            error_console.print(f"Editor exited with error: {e}")
            raise typer.Exit(code=1) from e
        finally:
            Path(tf_path).unlink(missing_ok=True)

        if not reply_body.strip():
            error_console.print("Empty reply, aborting.")
            raise typer.Exit(code=1)
    else:
        reply_body = reply_message
        if quote:
            quoted = "\n".join(f"> {line}" for line in original.body.split("\n"))
            reply_body = f"{reply_body}\n\n{quoted}"

    # Append reply-to link referencing the original message ID
    original_msgid = parse_message_id_from_filename(gemmail_file.name)
    if original_msgid:
        link = build_reply_link(original_msgid)
        reply_body = f"{reply_body.rstrip()}\n{link}\n"

    sender = build_sender_from_cert(cert) if cert else None

    async def _reply() -> None:
        try:
            with console.status(
                f"[bold blue]Replying to {reply_to.address}...",
            ):
                async with MisfinClient(
                    timeout=timeout,
                    client_cert=cert,
                    client_key=key,
                ) as client:
                    response = await client.send(
                        to=reply_to.address,
                        body=reply_body,
                        subject=reply_subject,
                        sender=sender,
                    )

            format_status_response(response.status, response.meta, console)
            if not is_success(response.status):
                raise typer.Exit(code=1)

        except typer.Exit:
            raise
        except ConnectionError as e:
            error_console.print(f"Connection error: {e}")
            raise typer.Exit(code=1) from e
        except TimeoutError as e:
            error_console.print(f"Timeout: {e}")
            raise typer.Exit(code=1) from e
        except Exception as e:
            error_console.print(f"Error: {e}")
            raise typer.Exit(code=1) from e

    asyncio.run(_reply())


@mail_app.command("block")
def mail_block(
    address: str = typer.Argument(..., help="Sender address to block (mailbox@hostname)"),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
) -> None:
    """Block a sender address from delivering mail."""
    if "@" not in address:
        error_console.print(f"Invalid address format: {address}")
        raise typer.Exit(code=1)

    address = address.strip().lower()
    mbox_path = _resolve_mailbox_path(mailbox_dir)
    blocked_file = mbox_path / ".blocked"

    existing = _read_blocked_set(blocked_file)
    if address in existing:
        console.print(f"[yellow]{address} is already blocked[/]")
        return

    existing.add(address)
    _write_blocked_set(blocked_file, existing)
    console.print(f"[green]Blocked {address}[/]")


@mail_app.command("unblock")
def mail_unblock(
    address: str = typer.Argument(..., help="Sender address to unblock"),
    mailbox_dir: Path | None = typer.Option(
        None, "--mailbox-dir", "-d", help="Mailbox directory"
    ),
) -> None:
    """Remove a sender address from the block list."""
    address = address.strip().lower()
    mbox_path = _resolve_mailbox_path(mailbox_dir)
    blocked_file = mbox_path / ".blocked"

    if not blocked_file.exists():
        console.print(f"[yellow]{address} was not blocked[/]")
        return

    existing = _read_blocked_set(blocked_file)
    if address not in existing:
        console.print(f"[yellow]{address} was not blocked[/]")
        return

    existing.discard(address)
    if existing:
        _write_blocked_set(blocked_file, existing)
    else:
        try:
            blocked_file.unlink()
        except OSError as e:
            error_console.print(
                f"Error removing .blocked file: {e}"
            )
            raise typer.Exit(code=1) from e
    console.print(f"[green]Unblocked {address}[/]")


def _resolve_mailbox_path(mailbox_dir: Path | None) -> Path:
    """Resolve to the current user's mailbox subdirectory path."""
    mailbox = get_current_mailbox(error_console)
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    mbox_path = resolved_dir / mailbox
    verify_mailbox_access(mbox_path, error_console)
    if not mbox_path.is_dir():
        error_console.print(f"Mailbox not found: {mailbox}")
        raise typer.Exit(code=1)
    return mbox_path


def _read_blocked_set(blocked_file: Path) -> set[str]:
    """Read the .blocked file into a set of lowercase addresses."""
    if not blocked_file.exists():
        return set()
    try:
        return {
            line.strip().lower()
            for line in blocked_file.read_text().splitlines()
            if line.strip()
        }
    except (OSError, UnicodeDecodeError) as e:
        error_console.print(f"Error reading .blocked file: {e}")
        raise typer.Exit(code=1) from e


def _write_blocked_set(blocked_file: Path, addresses: set[str]) -> None:
    """Write a set of addresses to the .blocked file."""
    try:
        blocked_file.write_text("\n".join(sorted(addresses)) + "\n")
    except OSError as e:
        error_console.print(f"Error writing .blocked file: {e}")
        raise typer.Exit(code=1) from e


def _resolve_message_path(
    message: str,
    mailbox_dir: Path | None,
) -> Path:
    """Resolve a message argument (index or file path) to a Path."""
    try:
        index = int(message)
    except ValueError:
        index = None

    if index is not None:
        resolved_mailbox = get_current_mailbox(error_console)
        resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
        verify_mailbox_access(
            resolved_dir / resolved_mailbox, error_console
        )
        messages = list_messages(resolved_dir, resolved_mailbox, error_console)
        if index < 1 or index > len(messages):
            error_console.print(
                f"Invalid message index: {index} (valid range: 1-{len(messages)})"
            )
            raise typer.Exit(code=1)
        return messages[index - 1][0]

    gemmail_file = Path(message).resolve()
    if not gemmail_file.exists():
        error_console.print(f"File not found: {gemmail_file}")
        raise typer.Exit(code=1)
    return gemmail_file
