"""Shared test fixtures."""

import datetime
import socket
import ssl
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from titlani.identity.certificate import generate_identity_cert


@pytest.fixture
def client_ssl_context() -> ssl.SSLContext:
    """SSL context that accepts all certificates (for testing)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


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
