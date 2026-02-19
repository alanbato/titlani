"""Shared test fixtures."""

import datetime
import socket
from collections.abc import Callable
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.x509.oid import NameOID

from titlani.content.gemmail import GemmailMessage, MisfinAddress
from titlani.identity.certificate import generate_identity_cert
from titlani.protocol.request import MisfinRequest


@pytest.fixture
def unused_tcp_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture
def test_identity_cert(tmp_path: Path) -> tuple[Path, Path]:
    """Generate a test identity certificate."""
    cert_pem, key_pem = generate_identity_cert(
        mailbox="testuser",
        hostname="test.example.com",
        blurb="Test User",
    )
    cert_path = tmp_path / "test.pem"
    key_path = tmp_path / "test.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    return cert_path, key_path


@pytest.fixture
def test_cert(test_identity_cert: tuple[Path, Path]) -> x509.Certificate:
    """Load the test certificate."""
    cert_path, _ = test_identity_cert
    return x509.load_pem_x509_certificate(cert_path.read_bytes())


def build_cn_only_cert(cn: str, san_dns: str | None = None) -> x509.Certificate:
    """Build a minimal self-signed cert with the given CN (and optional SAN).

    Useful for simulating Gemini-style certs that put user@host in CN
    instead of using Misfin USER_ID / SAN DNS fields.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
    )
    if san_dns:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san_dns)]),
            critical=False,
        )
    return builder.sign(key, hashes.SHA256())


@pytest.fixture
def sample_message_bytes() -> bytes:
    """A valid Misfin(C) message in bytes."""
    return (
        b"sender@example.com Sender Name\n"
        b"recipient@test.example.com\n"
        b"2024-01-15T10:30:00Z\n"
        b"# Hello\n"
        b"\n"
        b"This is a test message.\n"
    )


@pytest.fixture
def mailbox_dir(tmp_path: Path) -> Path:
    """Create and return a mailboxes directory."""
    d = tmp_path / "mailboxes"
    d.mkdir()
    return d


@pytest.fixture
def make_gemmail_message() -> Callable[..., GemmailMessage]:
    """Factory for GemmailMessage with sensible defaults."""

    def _make(
        senders: list[MisfinAddress] | None = None,
        recipients: list[MisfinAddress] | None = None,
        body: str = "Hello!\n",
    ) -> GemmailMessage:
        if senders is None:
            senders = [MisfinAddress("alice", "sender.example")]
        if recipients is None:
            recipients = [MisfinAddress("bob", "example.com")]
        return GemmailMessage(
            senders=senders,
            recipients=recipients,
            timestamps=[],
            body=body,
        )

    return _make


_DEFAULT_RAW_MESSAGE = (
    b"alice@sender.example\nbob@example.com\n2025-01-01T00:00:00Z\nHello!\n"
)


@pytest.fixture
def make_misfin_request() -> Callable[..., MisfinRequest]:
    """Factory for MisfinRequest with a valid gemmail body by default."""

    def _make(
        mailbox: str = "bob",
        hostname: str = "example.com",
        raw_message: bytes | None = None,
        content_length: int | None = None,
    ) -> MisfinRequest:
        if raw_message is None and content_length is None:
            raw_message = _DEFAULT_RAW_MESSAGE
        if raw_message is None:
            raw_message = b""
        if content_length is None:
            content_length = len(raw_message)
        return MisfinRequest(
            mailbox=mailbox,
            hostname=hostname,
            content_length=content_length,
            raw_message=raw_message,
        )

    return _make


@pytest.fixture
def generate_x25519_keypair() -> Callable[..., tuple[Path, Path]]:
    """Factory for X25519 PEM key files. Returns (priv_path, pub_path)."""

    def _generate(tmp_path: Path, mailbox: str) -> tuple[Path, Path]:
        private_key = X25519PrivateKey.generate()
        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        priv_path = tmp_path / f"{mailbox}.enc.key"
        pub_path = tmp_path / f"{mailbox}.enc.pub"
        priv_path.write_bytes(priv_pem)
        pub_path.write_bytes(pub_pem)
        return priv_path, pub_path

    return _generate
