"""Serve command."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from ...cli import display_server_config
from ...server.config import ServerConfig
from ...server.server import start_server

console = Console()
error_console = Console(stderr=True, style="bold red")


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
