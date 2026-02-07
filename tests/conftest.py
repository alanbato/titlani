"""Shared test fixtures."""

import socket
import ssl
from pathlib import Path

import pytest
from cryptography import x509

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
