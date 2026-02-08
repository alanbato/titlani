"""Tests for Misfin identity certificate utilities."""

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID

from titlani.identity.certificate import (
    MisfinIdentity,
    extract_identity,
    generate_identity_cert,
    normalize_fingerprint,
)


class TestMisfinIdentity:
    def test_address(self):
        ident = MisfinIdentity(mailbox="alice", hostname="example.com")
        assert ident.address == "alice@example.com"

    def test_long_form_with_blurb(self):
        ident = MisfinIdentity(mailbox="alice", hostname="example.com", blurb="Alice")
        assert ident.long_form == "Alice (alice@example.com)"

    def test_long_form_without_blurb(self):
        ident = MisfinIdentity(mailbox="alice", hostname="example.com")
        assert ident.long_form == "alice@example.com"

    def test_frozen(self):
        ident = MisfinIdentity(mailbox="alice", hostname="example.com")
        with pytest.raises(AttributeError):
            ident.mailbox = "bob"  # type: ignore[misc]


class TestGenerateIdentityCert:
    def test_generates_valid_cert(self):
        cert_pem, key_pem = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
            blurb="Alice Smith",
        )
        assert cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
        assert key_pem.startswith(b"-----BEGIN RSA PRIVATE KEY-----")

    def test_cert_has_user_id(self):
        cert_pem, _ = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
            blurb="Alice",
        )
        cert = x509.load_pem_x509_certificate(cert_pem)
        attrs = cert.subject.get_attributes_for_oid(NameOID.USER_ID)
        assert len(attrs) == 1
        assert attrs[0].value == "alice"

    def test_cert_has_cn_as_blurb(self):
        cert_pem, _ = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
            blurb="Alice Smith",
        )
        cert = x509.load_pem_x509_certificate(cert_pem)
        attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        assert len(attrs) == 1
        assert attrs[0].value == "Alice Smith"

    def test_cert_has_san_dns(self):
        cert_pem, _ = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
            blurb="Alice",
        )
        cert = x509.load_pem_x509_certificate(cert_pem)
        san_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san = san_ext.value
        dns_names = san.get_values_for_type(x509.DNSName)
        assert "example.com" in dns_names

    def test_cn_defaults_to_mailbox_when_no_blurb(self):
        cert_pem, _ = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
        )
        cert = x509.load_pem_x509_certificate(cert_pem)
        attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        assert attrs[0].value == "alice"


class TestExtractIdentity:
    def test_extract_from_generated_cert(self):
        cert_pem, _ = generate_identity_cert(
            mailbox="bob",
            hostname="mail.test",
            blurb="Bob The Builder",
        )
        cert = x509.load_pem_x509_certificate(cert_pem)
        identity = extract_identity(cert)
        assert identity.mailbox == "bob"
        assert identity.hostname == "mail.test"
        assert identity.blurb == "Bob The Builder"

    def test_extract_from_fixture(self, test_cert):
        identity = extract_identity(test_cert)
        assert identity.mailbox == "testuser"
        assert identity.hostname == "test.example.com"
        assert identity.blurb == "Test User"


class TestNormalizeFingerprint:
    def test_strips_algorithm_prefix(self):
        result = normalize_fingerprint("sha256:abc123def456")
        assert result == "abc123def456"

    def test_lowercases(self):
        result = normalize_fingerprint("ABC123DEF456")
        assert result == "abc123def456"

    def test_removes_non_hex_chars(self):
        result = normalize_fingerprint("ab:cd:12:34")
        assert result == "abcd1234"

    def test_full_tlacacoca_format(self):
        hex_part = "aabbccdd11223344" * 4
        fp = f"sha256:{hex_part}"
        result = normalize_fingerprint(fp)
        assert result == hex_part
        assert ":" not in result

    def test_already_normalized(self):
        fp = "abcdef0123456789"
        assert normalize_fingerprint(fp) == fp

    def test_empty_string(self):
        assert normalize_fingerprint("") == ""
