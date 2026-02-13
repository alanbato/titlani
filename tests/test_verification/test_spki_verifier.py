"""Tests for SPKIVerifier."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa

from titlani.content.gemmail import MisfinAddress
from titlani.verification.cache import SenderVerificationCache
from titlani.verification.spki_verifier import SPKIVerifier, extract_spki_hash


@pytest.fixture
def cache() -> SenderVerificationCache:
    c = SenderVerificationCache()
    yield c
    c.close()


def _addr(mailbox: str = "alice", hostname: str = "example.com") -> MisfinAddress:
    return MisfinAddress(mailbox=mailbox, hostname=hostname)


FAKE_SPKI = "a" * 64


def _make_cert(
    key: rsa.RSAPrivateKey | None = None, cn: str = "test"
) -> x509.Certificate:
    if key is None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)]))
        .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )


class TestExtractSPKIHash:
    def test_returns_hex_string(self) -> None:
        cert = _make_cert()
        result = extract_spki_hash(cert)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_key_same_hash(self) -> None:
        """Two certs with the same key should produce the same SPKI hash."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert1 = _make_cert(key=key, cn="test1")
        cert2 = _make_cert(key=key, cn="test2")
        assert extract_spki_hash(cert1) == extract_spki_hash(cert2)

    def test_different_keys_different_hash(self) -> None:
        cert1 = _make_cert()
        cert2 = _make_cert()
        assert extract_spki_hash(cert1) != extract_spki_hash(cert2)


class TestSPKIVerifierFirstContact:
    async def test_first_contact_trusts_and_caches(
        self, cache: SenderVerificationCache
    ) -> None:
        verifier = SPKIVerifier(cache=cache)
        with patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock:
            mock.return_value = FAKE_SPKI
            result = await verifier.verify_sender(_addr())

        assert result.verified is True
        assert result.fingerprint == FAKE_SPKI
        assert cache.get_server_spki("example.com") == FAKE_SPKI


class TestSPKIVerifierCacheHit:
    async def test_cache_hit_skips_network(self, cache: SenderVerificationCache) -> None:
        cache.add_server_spki("example.com", FAKE_SPKI)
        verifier = SPKIVerifier(cache=cache)
        with patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock:
            result = await verifier.verify_sender(_addr())

        assert result.verified is True
        assert result.cached is True
        assert result.fingerprint == FAKE_SPKI
        mock.assert_not_called()


class TestSPKIKeyChange:
    async def test_reject_policy_returns_unverified(
        self, cache: SenderVerificationCache
    ) -> None:
        # Seed an expired entry so get_server_spki returns None
        # but get_last_server_spki returns the old value.
        cache.add_server_spki("example.com", "old_spki_hash")
        # Expire the entry by patching the TTL-aware read
        verifier = SPKIVerifier(cache=cache, on_spki_change="reject")
        with (
            patch.object(cache, "get_server_spki", return_value=None),
            patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock,
        ):
            mock.return_value = "new_spki_hash"
            result = await verifier.verify_sender(_addr())

        assert result.verified is False
        assert "changed" in result.reason.lower()

    async def test_accept_policy_updates_cache(
        self, cache: SenderVerificationCache
    ) -> None:
        cache.add_server_spki("example.com", "old_spki_hash")
        verifier = SPKIVerifier(cache=cache, on_spki_change="accept")
        with (
            patch.object(cache, "get_server_spki", return_value=None),
            patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock,
        ):
            mock.return_value = "new_spki_hash"
            result = await verifier.verify_sender(_addr())

        assert result.verified is True
        assert result.fingerprint == "new_spki_hash"
        # Cache should be updated
        assert cache.get_server_spki("example.com") == "new_spki_hash"

    async def test_same_key_after_expiry_refreshes(
        self, cache: SenderVerificationCache
    ) -> None:
        """When cache expires but key is the same, refresh the timestamp."""
        cache.add_server_spki("example.com", FAKE_SPKI)
        verifier = SPKIVerifier(cache=cache)
        with (
            patch.object(cache, "get_server_spki", return_value=None),
            patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock,
        ):
            mock.return_value = FAKE_SPKI
            result = await verifier.verify_sender(_addr())

        assert result.verified is True
        assert result.fingerprint == FAKE_SPKI


class TestSPKIVerifierErrors:
    async def test_timeout_returns_unverified(
        self, cache: SenderVerificationCache
    ) -> None:
        verifier = SPKIVerifier(cache=cache)
        with patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock:
            mock.side_effect = TimeoutError()
            result = await verifier.verify_sender(_addr())

        assert result.verified is False
        assert "timed out" in result.reason.lower()

    async def test_connection_error_returns_unverified(
        self, cache: SenderVerificationCache
    ) -> None:
        verifier = SPKIVerifier(cache=cache)
        with patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock:
            mock.side_effect = OSError("Connection refused")
            result = await verifier.verify_sender(_addr())

        assert result.verified is False
        assert "connection error" in result.reason.lower()

    async def test_no_peer_cert_returns_unverified(
        self, cache: SenderVerificationCache
    ) -> None:
        verifier = SPKIVerifier(cache=cache)
        with patch.object(verifier, "_fetch_server_spki", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await verifier.verify_sender(_addr())

        assert result.verified is False
        assert "certificate" in result.reason.lower()
