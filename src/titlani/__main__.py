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
    mailbox_dir: Path = typer.Argument(
        ...,
        help="Path to mailbox directory",
        exists=True,
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
    mailbox: str | None = typer.Option(
        None,
        "--mailbox",
        "-m",
        help="Filter by specific mailbox name",
    ),
) -> None:
    """List messages in a mailbox directory."""
    messages: list[tuple[Path, GemmailMessage]] = []

    if mailbox:
        mbox_path = mailbox_dir / mailbox
        if not mbox_path.is_dir():
            error_console.print(f"Mailbox not found: {mailbox}")
            raise typer.Exit(code=1)
        search_paths = [mbox_path]
    else:
        search_paths = sorted(p for p in mailbox_dir.iterdir() if p.is_dir())

    for mbox_path in search_paths:
        for gemmail_file in sorted(mbox_path.glob("*.gemmail"), reverse=True):
            try:
                msg = GemmailMessage.from_bytes(gemmail_file.read_bytes())
                messages.append((gemmail_file, msg))
            except ValueError:
                error_console.print(
                    f"[yellow]Skipping invalid file: {gemmail_file.name}[/]"
                )

    display_gemmail_list(messages, console)


@mail_app.command("read")
def mail_read(
    gemmail_file: Path = typer.Argument(
        ...,
        help="Path to .gemmail file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Read and display a gemmail message."""
    try:
        msg = GemmailMessage.from_bytes(gemmail_file.read_bytes())
        display_gemmail_message(msg, console)
    except ValueError as e:
        error_console.print(f"Invalid gemmail format: {e}")
        raise typer.Exit(code=1) from e


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
