"""Mailing list support for the Misfin server."""

import os
import re
from pathlib import Path

from tlacacoca import get_logger

from ..content.gemmail import GemmailMessage
from ..identity.certificate import generate_identity_cert

logger = get_logger(__name__)

SUBSCRIBERS_FILE = "subscribers.txt"
SUBSCRIPTION_DB_FILE = "subscription_pending.db"
_LIST_CERT_FILE = ".list-identity.crt"
_LIST_KEY_FILE = ".list-identity.key"


def is_mailing_list(mailbox_path: Path) -> bool:
    """Check if a mailbox directory contains the subscribers.txt marker."""
    return (mailbox_path / SUBSCRIBERS_FILE).exists()


def load_subscribers(mailbox_path: Path) -> list[str]:
    """Parse subscribers.txt into a list of lowercase addresses.

    One address per line. Blank lines and lines starting with # are
    ignored.  Returns an empty list when the file is missing or
    unreadable.
    """
    subscribers_file = mailbox_path / SUBSCRIBERS_FILE
    if not subscribers_file.exists():
        return []

    try:
        lines = subscribers_file.read_text().strip().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        logger.error(
            "list_subscribers_read_failed",
            mailbox_path=str(mailbox_path),
            error=str(e),
        )
        return []

    addresses: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+", line):
            addresses.append(line.lower())
        else:
            logger.warning(
                "list_invalid_subscriber_address",
                address=line,
                file=str(subscribers_file),
            )
    return addresses


def add_subscriber(mailbox_path: Path, address: str) -> bool:
    """Append *address* to subscribers.txt. Returns False if already present."""
    address = address.strip().lower()
    existing = set(load_subscribers(mailbox_path))
    if address in existing:
        return False
    subscribers_file = mailbox_path / SUBSCRIBERS_FILE
    with subscribers_file.open("a") as f:
        f.write(f"{address}\n")
    return True


def remove_subscriber(mailbox_path: Path, address: str) -> bool:
    """Remove *address* from subscribers.txt. Returns False if not found."""
    address = address.strip().lower()
    existing = set(load_subscribers(mailbox_path))
    if address not in existing:
        return False
    subscribers_file = mailbox_path / SUBSCRIBERS_FILE
    lines = subscribers_file.read_text().splitlines()
    new_lines = [line for line in lines if line.strip().lower() != address]
    subscribers_file.write_text("\n".join(new_lines) + "\n")
    return True


def is_subscriber(sender_addr: str, subscribers: list[str]) -> bool:
    """Check if sender is in the subscriber list (case-insensitive)."""
    return sender_addr.lower() in subscribers


def should_prevent_loop(message: GemmailMessage, list_address: str) -> bool:
    """Return True if the list address already appears in recipients."""
    list_addr_lower = list_address.lower()
    return any(r.address.lower() == list_addr_lower for r in message.recipients)


def get_or_create_list_identity(
    mailbox_path: Path,
    mailbox: str,
    hostname: str,
) -> tuple[Path, Path]:
    """Return (cert_path, key_path) for a mailing list identity.

    Generates a new identity certificate on first call; reuses the
    existing files on subsequent calls.
    """
    cert_path = mailbox_path / _LIST_CERT_FILE
    key_path = mailbox_path / _LIST_KEY_FILE

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    cert_pem, key_pem = generate_identity_cert(
        mailbox=mailbox,
        hostname=hostname,
        blurb=f"{mailbox} mailing list",
    )

    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    os.chmod(cert_path, 0o600)
    os.chmod(key_path, 0o600)

    logger.info(
        "list_identity_created",
        list_address=f"{mailbox}@{hostname}",
    )
    return cert_path, key_path
