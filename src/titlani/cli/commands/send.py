"""Send command."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from ...cli import format_status_response
from ...cli._helpers import build_sender_from_cert, validate_cert_key_pair
from ...client.session import MisfinClient
from ...protocol.status import is_success

console = Console()
error_console = Console(stderr=True, style="bold red")


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
    validate_cert_key_pair(cert, key, error_console)

    sender = build_sender_from_cert(cert) if cert else None

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

    asyncio.run(_send())
