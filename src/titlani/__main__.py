"""Titlani Misfin(C) Protocol CLI."""

import asyncio
from importlib.metadata import version as get_version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .client.session import MisfinClient
from .content.gemmail import MisfinAddress
from .identity.certificate import (
    extract_identity,
    generate_identity_cert,
    normalize_fingerprint,
)
from .protocol.constants import DEFAULT_PORT
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

                if response.status == 20:
                    console.print(
                        f"[green]Message delivered[/] (fingerprint: {response.meta})"
                    )
                elif 30 <= response.status < 40:
                    console.print(f"[yellow]Redirect:[/] {response.meta}")
                else:
                    console.print(f"[red][{response.status}][/] {response.meta}")
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
        from tlacacoca import load_certificate

        cert = load_certificate(cert_file)
        identity = extract_identity(cert)
        from tlacacoca import get_certificate_fingerprint

        fp = normalize_fingerprint(get_certificate_fingerprint(cert))

        console.print("\n[bold green]Identity certificate generated![/]\n")

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")
        table.add_row("Address", identity.address)
        table.add_row("Blurb", identity.blurb)
        table.add_row("Certificate", str(cert_file))
        table.add_row("Private key", str(key_file))
        table.add_row("Fingerprint", fp[:32] + "...")

        console.print(table)

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

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")

        table.add_row("Address", identity.address)
        table.add_row("Blurb", identity.blurb)
        table.add_row("Hostname", identity.hostname)
        table.add_row("Fingerprint", fp)
        table.add_row("Not Before", info["not_before"])
        table.add_row("Not After", info["not_after"])

        console.print(table)

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

    if not hosts:
        console.print("[yellow]No known hosts in TOFU database.[/]")
        return

    table = Table(title="Known Hosts (TOFU)")
    table.add_column("Hostname", style="cyan")
    table.add_column("Port", justify="right")
    table.add_column("Fingerprint", style="dim")
    table.add_column("First Seen")
    table.add_column("Last Seen")

    for host_info in hosts:
        table.add_row(
            host_info["hostname"],
            str(host_info["port"]),
            host_info["fingerprint"][:16] + "...",
            host_info["first_seen"][:10],
            host_info["last_seen"][:10],
        )

    console.print(table)


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

    if db.revoke(tofu_hostname, effective_port):
        console.print(
            f"[green]Revoked certificate for {tofu_hostname}:{effective_port}[/]"
        )
    else:
        console.print(f"[yellow]Host {tofu_hostname}:{effective_port} not in database[/]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold cyan]Titlani[/] Misfin(C) Protocol Client & Server")
    console.print(f"[bold]Version:[/] {get_version('titlani')}")
    console.print("[bold]Protocol:[/] Misfin(C)")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
