"""Titlani Misfin(C) Protocol CLI."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from .cli import (
    confirm_action,
    display_gemmail_list,
    display_gemmail_message,
    display_identity_info,
    display_server_config,
    display_tofu_list,
    display_verification_list,
    display_version_info,
    format_status_response,
)
from .cli.mailbox import list_messages, resolve_mailbox_dir, resolve_mailbox_name
from .client.session import MisfinClient
from .content.gemmail import GemmailMessage, MisfinAddress
from .identity.certificate import (
    extract_identity,
    generate_identity_cert,
    normalize_fingerprint,
)
from .protocol.constants import DEFAULT_PORT
from .protocol.status import is_success
from .server.config import ServerConfig
from .server.server import start_server

console = Console()
error_console = Console(stderr=True, style="bold red")

app = typer.Typer(
    name="titlani",
    help="Titlani - Misfin(C) mail protocol client and server",
    add_completion=True,
    no_args_is_help=True,
)


@app.command()
def send(
    to: str = typer.Argument(..., help="Recipient address (mailbox@hostname)"),
    message: str = typer.Argument(..., help="Message body"),
    subject: str | None = typer.Option(None, "--subject", "-s", help="Message subject"),
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
    timeout: float = typer.Option(
        30.0, "--timeout", "-t", help="Request timeout in seconds"
    ),
) -> None:
    """Send a Misfin message."""
    if cert and not key:
        error_console.print("Error: --key is required when --cert is provided")
        raise typer.Exit(code=1)
    if key and not cert:
        error_console.print("Error: --cert is required when --key is provided")
        raise typer.Exit(code=1)

    # Build sender address from cert if provided
    sender = None
    if cert:
        from tlacacoca import load_certificate

        sender_cert = load_certificate(cert)
        identity = extract_identity(sender_cert)
        sender = MisfinAddress(
            mailbox=identity.mailbox,
            hostname=identity.hostname,
            blurb=identity.blurb,
        )

    async def _send() -> None:
        try:
            with console.status(
                f"[bold blue]Sending to {to}...",
            ):
                async with MisfinClient(
                    timeout=timeout,
                    client_cert=cert,
                    client_key=key,
                ) as client:
                    response = await client.send(
                        to=to,
                        body=message,
                        subject=subject,
                        sender=sender,
                    )

            format_status_response(response.status, response.meta, console)
            if not is_success(response.status):
                raise typer.Exit(code=1)

        except ConnectionError as e:
            error_console.print(f"Connection error: {e}")
            raise typer.Exit(code=1) from e
        except TimeoutError as e:
            error_console.print(f"Timeout: {e}")
            raise typer.Exit(code=1) from e
        except Exception as e:
            error_console.print(f"Error: {e}")
            raise typer.Exit(code=1) from e

    asyncio.run(_send())


@app.command()
def serve(
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to TOML configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    host: str | None = typer.Option(None, "--host", "-h", help="Server host address"),
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
    hostname: str | None = typer.Option(
        None, "--hostname", help="Server hostname for mail routing"
    ),
    cert: Path | None = typer.Option(
        None,
        "--cert",
        help="Path to TLS certificate file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    key: Path | None = typer.Option(
        None,
        "--key",
        help="Path to TLS private key file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    mailbox_dir: Path | None = typer.Option(
        None,
        "--mailbox-dir",
        help="Directory for storing mailboxes",
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    ),
) -> None:
    """Start a Misfin server."""

    async def _serve() -> None:
        try:
            if config_file:
                config = ServerConfig.from_toml(config_file)
            else:
                config = ServerConfig()

            # CLI overrides
            if host is not None:
                config.host = host
            if port is not None:
                config.port = port
            if hostname is not None:
                config.hostname = hostname
            if cert is not None:
                config.certfile = cert
            if key is not None:
                config.keyfile = key
            if mailbox_dir is not None:
                config.mailbox_dir = mailbox_dir

            display_server_config(config, console)
            await start_server(config, log_level=log_level)

        except ValueError as e:
            error_console.print(f"Configuration error: {e}")
            raise typer.Exit(code=1) from e
        except OSError as e:
            error_console.print(f"Server error: {e}")
            raise typer.Exit(code=1) from e
        except KeyboardInterrupt:
            console.print("\n[bold blue]Shutting down...[/]")
            raise typer.Exit(code=0) from None

    asyncio.run(_serve())


# Identity command group
identity_app = typer.Typer(
    help="Manage Misfin identity certificates",
    no_args_is_help=True,
)
app.add_typer(identity_app, name="identity")


@identity_app.command("generate")
def identity_generate(
    mailbox: str = typer.Argument(..., help="Mailbox name (e.g., alice)"),
    identity_hostname: str = typer.Argument(..., help="Hostname (e.g., example.com)"),
    blurb: str = typer.Option("", "--blurb", "-b", help="Human-readable description"),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory (default: current directory)",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    valid_days: int = typer.Option(
        365, "--valid-days", help="Certificate validity in days"
    ),
    key_size: int = typer.Option(2048, "--key-size", help="RSA key size in bits"),
    with_encryption_key: bool = typer.Option(
        False,
        "--with-encryption-key",
        help="Also generate an X25519 keypair for at-rest encryption",
    ),
) -> None:
    """Generate a Misfin identity certificate."""
    import os
    import stat

    if output_dir is None:
        output_dir = Path.cwd()

    output_dir.mkdir(parents=True, exist_ok=True)

    cert_file = output_dir / f"{mailbox}.pem"
    key_file = output_dir / f"{mailbox}.key"

    try:
        cert_pem, key_pem = generate_identity_cert(
            mailbox=mailbox,
            hostname=identity_hostname,
            blurb=blurb,
            key_size=key_size,
            valid_days=valid_days,
        )

        cert_file.write_bytes(cert_pem)
        key_file.write_bytes(key_pem)
        os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)

        # Load and display info
        from tlacacoca import (
            get_certificate_fingerprint,
            get_certificate_info,
            load_certificate,
        )

        cert = load_certificate(cert_file)
        identity = extract_identity(cert)
        fp = normalize_fingerprint(get_certificate_fingerprint(cert))
        info = get_certificate_info(cert)

        console.print()
        display_identity_info(
            identity,
            info,
            fp,
            console,
            cert_file=cert_file,
            key_file=key_file,
            title="Identity Certificate Generated",
        )

        if with_encryption_key:
            from .identity.certificate import generate_encryption_keypair

            pub_pem, priv_pem = generate_encryption_keypair()
            enc_key_file = output_dir / f"{mailbox}.enc.key"
            enc_pub_file = output_dir / f"{mailbox}.enc.pub"
            enc_key_file.write_bytes(priv_pem)
            enc_pub_file.write_bytes(pub_pem)
            os.chmod(enc_key_file, stat.S_IRUSR | stat.S_IWUSR)
            console.print(f"[green]Encryption private key:[/] {enc_key_file}")
            console.print(f"[green]Encryption public key:[/]  {enc_pub_file}")

    except Exception as e:
        error_console.print(f"Error generating certificate: {e}")
        raise typer.Exit(code=1) from e


@identity_app.command("info")
def identity_info(
    cert_file: Path = typer.Argument(
        ...,
        help="Path to certificate file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Show identity information from a certificate."""
    from tlacacoca import (
        get_certificate_fingerprint,
        get_certificate_info,
        load_certificate,
    )

    try:
        cert = load_certificate(cert_file)
        identity = extract_identity(cert)
        info = get_certificate_info(cert)
        fp = normalize_fingerprint(get_certificate_fingerprint(cert))

        display_identity_info(identity, info, fp, console)

    except Exception as e:
        error_console.print(f"Error reading certificate: {e}")
        raise typer.Exit(code=1) from e


# TOFU command group
tofu_app = typer.Typer(
    help="Manage TOFU certificate database",
    no_args_is_help=True,
)
app.add_typer(tofu_app, name="tofu")


@tofu_app.command("list")
def tofu_list() -> None:
    """List all known hosts in TOFU database."""
    from tlacacoca import TOFUDatabase

    db = TOFUDatabase()
    hosts = db.list_hosts()
    display_tofu_list(hosts, console)


@tofu_app.command("revoke")
def tofu_revoke(
    tofu_hostname: str = typer.Argument(..., help="Hostname to revoke"),
    port: int | None = typer.Option(
        None,
        "--port",
        "-p",
        help=f"Port number (default: {DEFAULT_PORT})",
    ),
) -> None:
    """Remove a host from the TOFU database."""
    from tlacacoca import TOFUDatabase

    db = TOFUDatabase()
    effective_port = port if port is not None else DEFAULT_PORT

    if not confirm_action(
        f"Revoke certificate for [cyan]{tofu_hostname}:{effective_port}[/]?",
        console,
    ):
        console.print("[dim]Cancelled.[/]")
        return

    if db.revoke(tofu_hostname, effective_port):
        console.print(
            f"[green]Revoked certificate for {tofu_hostname}:{effective_port}[/]"
        )
    else:
        console.print(f"[yellow]Host {tofu_hostname}:{effective_port} not in database[/]")


# Mail command group
mail_app = typer.Typer(
    help="Read stored mail",
    no_args_is_help=True,
)
app.add_typer(mail_app, name="mail")


@mail_app.command("list")
def mail_list(
    mailbox_dir: Path | None = typer.Argument(
        None,
        help="Path to mailbox directory (auto-detected from config if omitted)",
    ),
    mailbox: str | None = typer.Option(
        None,
        "--mailbox",
        "-m",
        help="Filter by specific mailbox name (defaults to $USER)",
    ),
) -> None:
    """List messages in a mailbox directory."""
    resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
    resolved_mailbox = resolve_mailbox_name(mailbox)
    messages = list_messages(resolved_dir, resolved_mailbox, error_console)
    display_gemmail_list(messages, console)


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
        help="Mailbox directory (for index resolution)",
    ),
    mailbox: str | None = typer.Option(
        None,
        "--mailbox",
        "-m",
        help="Mailbox name (for index resolution, defaults to $USER)",
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
    # Resolve message argument: index or file path
    try:
        index = int(message)
    except ValueError:
        index = None

    if index is not None:
        resolved_dir = resolve_mailbox_dir(mailbox_dir, error_console)
        resolved_mailbox = resolve_mailbox_name(mailbox)
        messages = list_messages(resolved_dir, resolved_mailbox, error_console)
        if index < 1 or index > len(messages):
            error_console.print(
                f"Invalid message index: {index} (valid range: 1-{len(messages)})"
            )
            raise typer.Exit(code=1)
        gemmail_file = messages[index - 1][0]
    else:
        gemmail_file = Path(message).resolve()
        if not gemmail_file.exists():
            error_console.print(f"File not found: {gemmail_file}")
            raise typer.Exit(code=1)

    try:
        if gemmail_file.suffix == ".enc":
            from .encryption.manager import EncryptionManager

            key_path = encryption_key
            if key_path is None:
                # Auto-discover <mailbox>.enc.key from parent dir
                mailbox_name = gemmail_file.parent.name
                mbox_dir = gemmail_file.parent.parent
                key_path = mbox_dir / f"{mailbox_name}.enc.key"
                if not key_path.exists():
                    error_console.print(
                        f"No encryption key found at {key_path}\n"
                        "Use --encryption-key / -e to specify the key path."
                    )
                    raise typer.Exit(code=1)

            decrypted = EncryptionManager.decrypt_with_key(
                key_path, gemmail_file.read_bytes()
            )
            msg = GemmailMessage.from_bytes(decrypted)
        else:
            msg = GemmailMessage.from_bytes(gemmail_file.read_bytes())
        display_gemmail_message(msg, console)
    except ValueError as e:
        error_console.print(f"Invalid gemmail format: {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        error_console.print(f"Error reading message: {e}")
        raise typer.Exit(code=1) from e


@mail_app.command("delete")
def mail_delete(
    files: list[Path] = typer.Argument(
        ...,
        help="Paths to .gemmail or .gemmail.enc files to delete",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete one or more stored messages."""
    if not force:
        file_list = "\n".join(f"  {f.name}" for f in files)
        if not confirm_action(
            f"Delete {len(files)} message(s)?\n{file_list}",
            console,
        ):
            console.print("[dim]Cancelled.[/]")
            return

    deleted = 0
    for filepath in files:
        try:
            filepath.unlink()
            deleted += 1
        except OSError as e:
            error_console.print(f"Error deleting {filepath.name}: {e}")

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
    import os
    import subprocess
    import tempfile

    if cert and not key:
        error_console.print("Error: --key is required when --cert is provided")
        raise typer.Exit(code=1)
    if key and not cert:
        error_console.print("Error: --cert is required when --key is provided")
        raise typer.Exit(code=1)

    # Read original message
    try:
        if gemmail_file.suffix == ".enc":
            from .encryption.manager import EncryptionManager

            key_path = encryption_key
            if key_path is None:
                mailbox_name = gemmail_file.parent.name
                mailbox_dir = gemmail_file.parent.parent
                key_path = mailbox_dir / f"{mailbox_name}.enc.key"
                if not key_path.exists():
                    error_console.print(
                        f"No encryption key found at {key_path}\n"
                        "Use --encryption-key / -e to specify the key path."
                    )
                    raise typer.Exit(code=1)

            decrypted = EncryptionManager.decrypt_with_key(
                key_path, gemmail_file.read_bytes()
            )
            original = GemmailMessage.from_bytes(decrypted)
        else:
            original = GemmailMessage.from_bytes(gemmail_file.read_bytes())
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
        # Open $EDITOR
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

    # Build sender from cert
    sender = None
    if cert:
        from tlacacoca import load_certificate

        sender_cert = load_certificate(cert)
        identity = extract_identity(sender_cert)
        sender = MisfinAddress(
            mailbox=identity.mailbox,
            hostname=identity.hostname,
            blurb=identity.blurb,
        )

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


# Verification command group
verification_app = typer.Typer(
    help="Manage sender verification cache",
    no_args_is_help=True,
)
app.add_typer(verification_app, name="verification")


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
    from .verification.cache import SenderVerificationCache

    cache = SenderVerificationCache(cache_path)
    try:
        entries = cache.list_verified()
        display_verification_list(entries, console)
    finally:
        cache.close()


@app.command()
def version() -> None:
    """Show version information."""
    display_version_info(console)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
