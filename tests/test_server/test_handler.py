"""Tests for FileMailboxHandler hardening."""

import stat

import pytest

from titlani.protocol.request import MisfinRequest
from titlani.protocol.status import StatusCode
from titlani.server.handler import FileMailboxHandler


def _make_valid_message() -> bytes:
    """Return a minimal valid gemmail message body."""
    return b"alice@sender.example\nbob@example.com\n2025-01-01T00:00:00Z\nHello!\n"


def _make_request(
    mailbox: str,
    hostname: str = "example.com",
    message: bytes | None = None,
) -> MisfinRequest:
    if message is None:
        message = _make_valid_message()
    return MisfinRequest(
        mailbox=mailbox,
        hostname=hostname,
        content_length=len(message),
        raw_message=message,
    )


class TestFilePermissions:
    async def test_written_gemmail_has_600_permissions(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        (mailbox_dir / "bob").mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
        )
        request = _make_request("bob")
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        files = list((mailbox_dir / "bob").glob("*.gemmail"))
        assert len(files) == 1
        file_mode = stat.S_IMODE(files[0].stat().st_mode)
        assert file_mode == 0o600


class TestMailboxSanitization:
    async def test_valid_mailbox_name(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        (mailbox_dir / "alice").mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
        )
        request = _make_request("alice")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    async def test_valid_mailbox_with_dots_and_dashes(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        (mailbox_dir / "alice.bob-carol_dave").mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
        )
        request = _make_request("alice.bob-carol_dave")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    @pytest.mark.parametrize(
        "mailbox",
        [
            "../etc",
            "foo/bar",
            "foo\\bar",
            "..\x00",
            "a\x00b",
            "..%2f",
            "",
        ],
    )
    async def test_traversal_names_rejected(self, tmp_path, mailbox):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
        )
        request = _make_request(mailbox)
        response = await handler.handle_message(request)
        assert response.status == StatusCode.BAD_REQUEST

    async def test_double_dot_name_rejected(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
        )
        request = _make_request("..")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.BAD_REQUEST

    async def test_probe_bypasses_sanitization(self, tmp_path):
        """Zero-length verification probes don't use mailbox path."""
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            identity_cert_fingerprint="abc123",
        )
        request = MisfinRequest(
            mailbox="../etc",
            hostname="example.com",
            content_length=0,
            raw_message=b"",
        )
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS
