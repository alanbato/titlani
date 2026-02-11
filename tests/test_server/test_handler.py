"""Tests for FileMailboxHandler hardening."""

import stat
from datetime import UTC, datetime, timedelta

import pytest

from titlani.content.gemmail import GemmailMessage, MisfinAddress
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

        files = list((mailbox_dir / "bob").glob("*.gemmail.new"))
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


class TestSenderBlocking:
    async def test_blocked_sender_rejected(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        mbox = mailbox_dir / "bob"
        mbox.mkdir()
        (mbox / ".blocked").write_text("alice@sender.example\n")

        handler = FileMailboxHandler(mailbox_dir=mailbox_dir, hostname="example.com")
        request = _make_request("bob")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.UNAUTHORIZED_SENDER

    async def test_unblocked_sender_accepted(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        mbox = mailbox_dir / "bob"
        mbox.mkdir()
        (mbox / ".blocked").write_text("evil@spam.example\n")

        handler = FileMailboxHandler(mailbox_dir=mailbox_dir, hostname="example.com")
        request = _make_request("bob")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    async def test_no_blocked_file_allows_all(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        (mailbox_dir / "bob").mkdir()

        handler = FileMailboxHandler(mailbox_dir=mailbox_dir, hostname="example.com")
        request = _make_request("bob")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    async def test_case_insensitive_matching(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        mbox = mailbox_dir / "bob"
        mbox.mkdir()
        (mbox / ".blocked").write_text("Alice@Sender.Example\n")

        handler = FileMailboxHandler(mailbox_dir=mailbox_dir, hostname="example.com")
        request = _make_request("bob")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.UNAUTHORIZED_SENDER

    async def test_empty_blocked_file_allows_all(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        mbox = mailbox_dir / "bob"
        mbox.mkdir()
        (mbox / ".blocked").write_text("\n\n")

        handler = FileMailboxHandler(mailbox_dir=mailbox_dir, hostname="example.com")
        request = _make_request("bob")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    async def test_multiple_blocked_addresses(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        mbox = mailbox_dir / "bob"
        mbox.mkdir()
        (mbox / ".blocked").write_text("alice@sender.example\nspam@evil.com\n")

        handler = FileMailboxHandler(mailbox_dir=mailbox_dir, hostname="example.com")
        request = _make_request("bob")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.UNAUTHORIZED_SENDER


class TestAutoReplyShould:
    def _make_message(
        self, sender="alice@sender.example", subject=None
    ) -> GemmailMessage:
        senders = []
        if sender:
            m, h = sender.split("@")
            senders = [MisfinAddress(m, h)]
        body = ""
        if subject:
            body = f"# {subject}\n\n"
        body += "Hello!\n"
        return GemmailMessage(
            senders=senders,
            recipients=[MisfinAddress("bob", "example.com")],
            timestamps=[datetime.now(UTC)],
            body=body,
        )

    def test_should_reply_when_auto_reply_file_exists(self, tmp_path):
        mbox = tmp_path / "bob"
        mbox.mkdir()
        (mbox / ".auto-reply").write_text("I'm away.")
        handler = FileMailboxHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            auto_reply_enabled=True,
        )
        msg = self._make_message()
        assert handler._should_auto_reply(mbox, msg) is True

    def test_should_not_reply_without_file(self, tmp_path):
        mbox = tmp_path / "bob"
        mbox.mkdir()
        handler = FileMailboxHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            auto_reply_enabled=True,
        )
        msg = self._make_message()
        assert handler._should_auto_reply(mbox, msg) is False

    def test_should_not_reply_to_auto_reply(self, tmp_path):
        mbox = tmp_path / "bob"
        mbox.mkdir()
        (mbox / ".auto-reply").write_text("I'm away.")
        handler = FileMailboxHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            auto_reply_enabled=True,
        )
        msg = self._make_message(subject="[Auto-Reply]")
        assert handler._should_auto_reply(mbox, msg) is False

    def test_should_not_reply_without_sender(self, tmp_path):
        mbox = tmp_path / "bob"
        mbox.mkdir()
        (mbox / ".auto-reply").write_text("I'm away.")
        handler = FileMailboxHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            auto_reply_enabled=True,
        )
        msg = self._make_message(sender="")
        # Empty sender list
        msg.senders = []
        assert handler._should_auto_reply(mbox, msg) is False

    def test_rate_limiting(self, tmp_path):
        mbox = tmp_path / "bob"
        mbox.mkdir()
        (mbox / ".auto-reply").write_text("I'm away.")
        handler = FileMailboxHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            auto_reply_enabled=True,
            auto_reply_interval=3600,
        )
        msg = self._make_message()
        # First message: should reply
        assert handler._should_auto_reply(mbox, msg) is True
        # Simulate having sent a reply recently
        handler._auto_reply_last_sent["alice@sender.example"] = datetime.now(UTC)
        # Second message: rate limited
        assert handler._should_auto_reply(mbox, msg) is False

    def test_rate_limit_expired(self, tmp_path):
        mbox = tmp_path / "bob"
        mbox.mkdir()
        (mbox / ".auto-reply").write_text("I'm away.")
        handler = FileMailboxHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            auto_reply_enabled=True,
            auto_reply_interval=3600,
        )
        msg = self._make_message()
        # Simulate old reply
        handler._auto_reply_last_sent["alice@sender.example"] = datetime.now(
            UTC
        ) - timedelta(hours=2)
        assert handler._should_auto_reply(mbox, msg) is True


class TestMailboxSanitizationProbe:
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
