"""Shared CLI helper utilities."""

from pathlib import Path

from rich.console import Console

from ..content.gemmail import GemmailMessage, MisfinAddress
from ..encryption.manager import EncryptionManager
from ..identity.certificate import extract_identity


def validate_cert_key_pair(
    cert: Path | None,
    key: Path | None,
    error_console: Console,
) -> None:
    """Validate that cert and key are both provided or both absent."""
    import typer

    if cert and not key:
        error_console.print("Error: --key is required when --cert is provided")
        raise typer.Exit(code=1)
    if key and not cert:
        error_console.print("Error: --cert is required when --key is provided")
        raise typer.Exit(code=1)


def resolve_identity(
    cert: Path | None,
    key: Path | None,
    error_console: Console,
) -> tuple[Path | None, Path | None]:
    """Resolve identity cert/key: explicit flags -> config file.

    Returns the resolved (cert, key) pair after validation.
    """
    if cert or key:
        validate_cert_key_pair(cert, key, error_console)
        return cert, key

    from .config import ClientConfig

    config = ClientConfig.load()
    if config is not None and config.certfile and config.keyfile:
        cert, key = config.certfile, config.keyfile

    validate_cert_key_pair(cert, key, error_console)
    return cert, key


def build_sender_from_cert(cert: Path) -> MisfinAddress:
    """Extract a MisfinAddress sender from an identity certificate."""
    from tlacacoca import load_certificate

    sender_cert = load_certificate(cert)
    identity = extract_identity(sender_cert)
    return MisfinAddress(
        mailbox=identity.mailbox,
        hostname=identity.hostname,
        blurb=identity.blurb,
    )


def read_encrypted_message(
    gemmail_file: Path,
    encryption_key: Path | None,
    error_console: Console,
) -> GemmailMessage:
    """Read and decrypt a .gemmail.enc file."""
    import typer

    key_path = encryption_key
    if key_path is None:
        mailbox_name = gemmail_file.parent.name
        mbox_dir = gemmail_file.parent.parent
        key_path = mbox_dir / f"{mailbox_name}.enc.key"
        if not key_path.exists():
            error_console.print(
                f"No encryption key found at {key_path}\n"
                "Use --encryption-key / -e to specify the key path."
            )
            raise typer.Exit(code=1)

    decrypted = EncryptionManager.decrypt_with_key(key_path, gemmail_file.read_bytes())
    return GemmailMessage.from_bytes(decrypted)
