"""Tests for FileMailboxHandler probe response."""

from pathlib import Path

from titlani.protocol.request import MisfinRequest
from titlani.protocol.status import StatusCode
from titlani.server.handler import FileMailboxHandler


class TestProbeResponse:
    async def test_zero_length_returns_fingerprint(self, tmp_path: Path) -> None:
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="test.example.com",
            identity_cert_fingerprint="abcdef1234567890",
        )

        request = MisfinRequest(
            mailbox="alice",
            hostname="test.example.com",
            content_length=0,
        )
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        assert response.meta == "abcdef1234567890"

    async def test_zero_length_no_fingerprint(self, tmp_path: Path) -> None:
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="test.example.com",
        )

        request = MisfinRequest(
            mailbox="alice",
            hostname="test.example.com",
            content_length=0,
        )
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        assert response.meta == ""

    async def test_zero_length_skips_mailbox_check(self, tmp_path: Path) -> None:
        """Probes succeed even if the mailbox directory doesn't exist."""
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        # NOTE: no "alice" subdirectory

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="test.example.com",
            identity_cert_fingerprint="abc123",
        )

        request = MisfinRequest(
            mailbox="alice",
            hostname="test.example.com",
            content_length=0,
        )
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

    async def test_zero_length_wrong_hostname_rejected(self, tmp_path: Path) -> None:
        """Probes for wrong hostname are rejected."""
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="test.example.com",
            identity_cert_fingerprint="abc123",
        )

        request = MisfinRequest(
            mailbox="alice",
            hostname="wrong.example.com",
            content_length=0,
        )
        response = await handler.handle_message(request)

        assert response.status == StatusCode.DOMAIN_NOT_SERVICED
