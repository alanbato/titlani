"""Tests for ProbeVerifier."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from titlani.content.gemmail import MisfinAddress
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode
from titlani.verification.cache import SenderVerificationCache
from titlani.verification.verifier import (
    ProbeVerifier,
    VerificationMode,
)


class TestVerificationMode:
    def test_values(self) -> None:
        assert VerificationMode.OFF == "off"
        assert VerificationMode.OPTIONAL == "optional"
        assert VerificationMode.REQUIRED == "required"


class TestProbeVerifier:
    def _make_verifier(
        self,
        cache: SenderVerificationCache,
        cert_path: Path,
        key_path: Path,
    ) -> ProbeVerifier:
        return ProbeVerifier(
            cache=cache,
            identity_cert=cert_path,
            identity_key=key_path,
            timeout=5.0,
        )

    async def test_cache_hit(self, test_identity_cert: tuple[Path, Path]) -> None:
        cert, key = test_identity_cert
        cache = SenderVerificationCache()
        cache.add_verified("alice@example.com", "abc123")

        verifier = self._make_verifier(cache, cert, key)
        addr = MisfinAddress(mailbox="alice", hostname="example.com")
        result = await verifier.verify_sender(addr)

        assert result.verified is True
        assert result.fingerprint == "abc123"
        assert result.cached is True
        cache.close()

    async def test_probe_success(self, test_identity_cert: tuple[Path, Path]) -> None:
        cert, key = test_identity_cert
        cache = SenderVerificationCache()

        verifier = self._make_verifier(cache, cert, key)
        addr = MisfinAddress(mailbox="bob", hostname="example.org")

        mock_response = MisfinResponse(status=StatusCode.SUCCESS, meta="def456")
        with patch("titlani.verification.verifier.MisfinClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client._send_request.return_value = mock_response
            MockClient.return_value = mock_client

            result = await verifier.verify_sender(addr)

        assert result.verified is True
        assert result.fingerprint == "def456"
        assert result.cached is False
        # Should be cached now
        assert cache.get_fingerprint("bob@example.org") == "def456"
        cache.close()

    async def test_probe_failure(self, test_identity_cert: tuple[Path, Path]) -> None:
        cert, key = test_identity_cert
        cache = SenderVerificationCache()

        verifier = self._make_verifier(cache, cert, key)
        addr = MisfinAddress(mailbox="noone", hostname="example.com")

        mock_response = MisfinResponse(
            status=StatusCode.MAILBOX_NOT_FOUND, meta="Not found"
        )
        with patch("titlani.verification.verifier.MisfinClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client._send_request.return_value = mock_response
            MockClient.return_value = mock_client

            result = await verifier.verify_sender(addr)

        assert result.verified is False
        assert "status 51" in (result.reason or "")
        cache.close()

    async def test_probe_timeout(self, test_identity_cert: tuple[Path, Path]) -> None:
        cert, key = test_identity_cert
        cache = SenderVerificationCache()

        verifier = self._make_verifier(cache, cert, key)
        addr = MisfinAddress(mailbox="slow", hostname="example.com")

        with patch("titlani.verification.verifier.MisfinClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client._send_request.side_effect = TimeoutError()
            MockClient.return_value = mock_client

            result = await verifier.verify_sender(addr)

        assert result.verified is False
        assert "timed out" in (result.reason or "").lower()
        cache.close()

    async def test_probe_connection_error(
        self, test_identity_cert: tuple[Path, Path]
    ) -> None:
        cert, key = test_identity_cert
        cache = SenderVerificationCache()

        verifier = self._make_verifier(cache, cert, key)
        addr = MisfinAddress(mailbox="unreachable", hostname="nohost.invalid")

        with patch("titlani.verification.verifier.MisfinClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client._send_request.side_effect = ConnectionError("refused")
            MockClient.return_value = mock_client

            result = await verifier.verify_sender(addr)

        assert result.verified is False
        assert "error" in (result.reason or "").lower()
        cache.close()
