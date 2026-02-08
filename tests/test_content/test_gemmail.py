"""Tests for GemmailMessage and MisfinAddress."""

import pytest

from titlani.content.gemmail import GemmailMessage, MisfinAddress


class TestMisfinAddress:
    def test_parse_simple(self):
        addr = MisfinAddress.parse("alice@example.com")
        assert addr.mailbox == "alice"
        assert addr.hostname == "example.com"
        assert addr.blurb == ""

    def test_parse_with_blurb(self):
        addr = MisfinAddress.parse("alice@example.com Alice Smith")
        assert addr.mailbox == "alice"
        assert addr.hostname == "example.com"
        assert addr.blurb == "Alice Smith"

    def test_parse_strips_whitespace(self):
        addr = MisfinAddress.parse("  alice@example.com  ")
        assert addr.mailbox == "alice"
        assert addr.hostname == "example.com"

    def test_parse_empty_raises(self):
        with pytest.raises(ValueError, match="Empty address"):
            MisfinAddress.parse("")

    def test_parse_no_at_raises(self):
        with pytest.raises(ValueError, match="Invalid address"):
            MisfinAddress.parse("alice")

    def test_parse_comma_in_blurb_raises(self):
        with pytest.raises(ValueError, match="commas"):
            MisfinAddress.parse("alice@example.com Alice, Smith")

    def test_parse_at_in_blurb_raises(self):
        with pytest.raises(ValueError, match="@"):
            MisfinAddress.parse("alice@example.com alice@other")

    def test_address_property(self):
        addr = MisfinAddress(mailbox="alice", hostname="example.com")
        assert addr.address == "alice@example.com"

    def test_long_form_with_blurb(self):
        addr = MisfinAddress(mailbox="alice", hostname="example.com", blurb="Alice")
        assert addr.long_form == "Alice (alice@example.com)"

    def test_long_form_without_blurb(self):
        addr = MisfinAddress(mailbox="alice", hostname="example.com")
        assert addr.long_form == "alice@example.com"

    def test_str_with_blurb(self):
        addr = MisfinAddress(mailbox="alice", hostname="example.com", blurb="Alice")
        assert str(addr) == "alice@example.com Alice"

    def test_str_without_blurb(self):
        addr = MisfinAddress(mailbox="alice", hostname="example.com")
        assert str(addr) == "alice@example.com"


class TestGemmailMessage:
    def test_from_bytes_full_message(self):
        data = (
            b"sender@example.com Sender\n"
            b"recipient@mail.com\n"
            b"2024-01-15T10:30:00Z\n"
            b"# Hello\n"
            b"\n"
            b"Message body.\n"
        )
        msg = GemmailMessage.from_bytes(data)
        assert len(msg.senders) == 1
        assert msg.senders[0].mailbox == "sender"
        assert msg.senders[0].blurb == "Sender"
        assert len(msg.recipients) == 1
        assert msg.recipients[0].mailbox == "recipient"
        assert len(msg.timestamps) == 1
        assert msg.body == "# Hello\n\nMessage body.\n"

    def test_from_bytes_empty_metadata_lines(self):
        data = b"\n\n\nBody text.\n"
        msg = GemmailMessage.from_bytes(data)
        assert msg.senders == []
        assert msg.recipients == []
        assert msg.timestamps == []
        assert msg.body == "Body text.\n"

    def test_from_bytes_multiple_senders(self):
        data = (
            b"list@lists.com Mailing List, original@sender.com Original\n"
            b"recipient@mail.com\n"
            b"\n"
            b"Body.\n"
        )
        msg = GemmailMessage.from_bytes(data)
        assert len(msg.senders) == 2
        assert msg.senders[0].mailbox == "list"
        assert msg.senders[1].mailbox == "original"

    def test_from_bytes_multiple_recipients(self):
        data = b"sender@example.com\nalice@mail.com, bob@mail.com\n\nBody.\n"
        msg = GemmailMessage.from_bytes(data)
        assert len(msg.recipients) == 2

    def test_from_bytes_crlf_line_endings(self):
        data = b"sender@example.com\r\nrecipient@mail.com\r\n\r\nBody.\r\n"
        msg = GemmailMessage.from_bytes(data)
        assert len(msg.senders) == 1

    def test_from_bytes_cr_only_rejected(self):
        data = b"sender@example.com\rrecipient@mail.com\n\n\nBody.\n"
        with pytest.raises(ValueError, match="CR must only appear"):
            GemmailMessage.from_bytes(data)

    def test_from_bytes_invalid_utf8(self):
        with pytest.raises(ValueError, match="not valid UTF-8"):
            GemmailMessage.from_bytes(b"\xff\xfe\n\n\nBody.\n")

    def test_from_bytes_too_few_lines(self):
        with pytest.raises(ValueError, match="at least 3 metadata"):
            GemmailMessage.from_bytes(b"sender@example.com\nrecipient\n")

    def test_from_bytes_metadata_line_too_long(self):
        long_line = ("a" * 1020 + "@b.c").encode() + b"\n\n\nBody.\n"
        with pytest.raises(ValueError, match="exceeds"):
            GemmailMessage.from_bytes(long_line)

    def test_subject_extraction(self):
        data = b"\n\n\n# My Subject\n\nBody text.\n"
        msg = GemmailMessage.from_bytes(data)
        assert msg.subject == "My Subject"

    def test_subject_no_heading(self):
        data = b"\n\n\nNo heading here.\n"
        msg = GemmailMessage.from_bytes(data)
        assert msg.subject is None

    def test_to_bytes_roundtrip(self):
        data = (
            b"sender@example.com Sender\n"
            b"recipient@mail.com\n"
            b"2024-01-15T10:30:00Z\n"
            b"# Hello\n"
            b"\n"
            b"Message body.\n"
        )
        msg = GemmailMessage.from_bytes(data)
        result = msg.to_bytes()
        msg2 = GemmailMessage.from_bytes(result)
        assert len(msg2.senders) == len(msg.senders)
        assert msg2.senders[0].address == msg.senders[0].address
        assert len(msg2.recipients) == len(msg.recipients)
        assert msg2.body == msg.body
