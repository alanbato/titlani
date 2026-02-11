"""Identity certificate commands."""

import os
import shutil
import stat
from pathlib import Path

import typer
from platformdirs import user_config_path
from rich.console import Console

from ...cli import display_identity_info
from ...identity.certificate import (
    extract_identity,
    generate_identity_cert,
    normalize_fingerprint,
)
from ...server.config import ServerConfig

console = Console()
error_console = Console(stderr=True, style="bold red")

identity_app = typer.Typer(
    help="Manage Misfin identity certificates",
    no_args_is_help=True,
)


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
    install: bool = typer.Option(
        False,
        "--install",
        help="Copy the .pem to the server's identity cert directory for GMAP auth",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Server config path (default: ~/.config/titlani/server.toml)",
    ),
) -> None:
    """Generate a Misfin identity certificate."""
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
            from ...identity.certificate import generate_encryption_keypair

            pub_pem, priv_pem = generate_encryption_keypair()
            enc_key_file = output_dir / f"{mailbox}.enc.key"
            enc_pub_file = output_dir / f"{mailbox}.enc.pub"
            enc_key_file.write_bytes(priv_pem)
            enc_pub_file.write_bytes(pub_pem)
            os.chmod(enc_key_file, stat.S_IRUSR | stat.S_IWUSR)
            console.print(f"[green]Encryption private key:[/] {enc_key_file}")
            console.print(f"[green]Encryption public key:[/]  {enc_pub_file}")

        if install:
            config_path = config or (user_config_path("titlani") / "server.toml")
            if not config_path.exists():
                error_console.print(
                    f"Server config not found: {config_path}\n"
                    "Run [bold]titlani init[/] first or specify "
                    "--config."
                )
                raise typer.Exit(code=1)

            server_config = ServerConfig.from_toml(config_path)
            dest_dir = server_config.identity_cert_dir or server_config.mailbox_dir
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_pem = dest_dir / f"{mailbox}.pem"
            shutil.copy2(cert_file, dest_pem)
            console.print(f"\n[green]Installed:[/] {dest_pem}")

            # Ensure mailbox subdirectory exists
            mailbox_subdir = server_config.mailbox_dir / mailbox
            mailbox_subdir.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]Mailbox dir:[/] {mailbox_subdir}")

            console.print(
                f"\n[dim]Share with user:[/]\n"
                f"  Certificate: {cert_file}\n"
                f"  Private key: {key_file}"
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
