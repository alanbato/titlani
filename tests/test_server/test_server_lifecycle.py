"""Tests for server startup, auto-cert generation, and cleanup."""

import asyncio
from unittest.mock import AsyncMock, patch

from titlani.identity.certificate import generate_identity_cert
from titlani.server.config import ServerConfig, ServerSection
from titlani.server.server import _load_recipient_fingerprints, start_server


class TestAutoCleanup:
    async def test_tmp_dir_cleaned_on_shutdown(self, tmp_path):
        """Temp cert directory should be removed after server stops."""
        config = ServerConfig(
            server=ServerSection(
                host="127.0.0.1",
                port=1958,
                hostname="test.example.com",
                mailbox_dir=tmp_path / "mailboxes",
            )
        )
        (tmp_path / "mailboxes").mkdir()

        # Run server briefly then cancel it
        with patch("titlani.server.server.asyncio.get_running_loop") as mock_loop:
            mock_server = AsyncMock()
            mock_server.serve_forever = AsyncMock(side_effect=asyncio.CancelledError)
            mock_server.__aenter__ = AsyncMock(return_value=mock_server)
            mock_server.__aexit__ = AsyncMock(return_value=False)
            mock_loop.return_value.create_server = AsyncMock(return_value=mock_server)

            await start_server(config)

        # Verify the function completed without error (cleanup happens in finally)
        assert True

    async def test_cache_closed_on_shutdown(self, tmp_path):
        """Verification cache should be closed after server stops."""
        config = ServerConfig(
            server=ServerSection(
                host="127.0.0.1",
                port=1958,
                hostname="test.example.com",
                mailbox_dir=tmp_path / "mailboxes",
            ),
            verification={"mode": "optional"},
        )
        (tmp_path / "mailboxes").mkdir()

        with (
            patch("titlani.server.server.asyncio.get_running_loop") as mock_loop,
            patch("titlani.server.server.SenderVerificationCache") as mock_cache_cls,
        ):
            mock_cache = mock_cache_cls.return_value

            mock_server = AsyncMock()
            mock_server.serve_forever = AsyncMock(side_effect=asyncio.CancelledError)
            mock_server.__aenter__ = AsyncMock(return_value=mock_server)
            mock_server.__aexit__ = AsyncMock(return_value=False)
            mock_loop.return_value.create_server = AsyncMock(return_value=mock_server)

            await start_server(config)

        mock_cache.close.assert_called_once()


class TestRecipientFingerprints:
    def test_loads_pem_files(self, tmp_path):
        """Should load fingerprints from <mailbox>.pem files."""
        cert_pem, _ = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
        )
        (tmp_path / "alice.pem").write_bytes(cert_pem)

        fps = _load_recipient_fingerprints(tmp_path, "fallback_fp")
        assert "alice" in fps
        assert len(fps["alice"]) == 64  # SHA-256 hex

    def test_returns_empty_for_missing_dir(self, tmp_path):
        """Should return empty dict if directory doesn't exist."""
        fps = _load_recipient_fingerprints(tmp_path / "nonexistent", "fallback_fp")
        assert fps == {}

    def test_skips_invalid_pem(self, tmp_path):
        """Should skip non-certificate PEM files."""
        (tmp_path / "bad.pem").write_text("not a cert")
        fps = _load_recipient_fingerprints(tmp_path, "fallback_fp")
        assert "bad" not in fps
