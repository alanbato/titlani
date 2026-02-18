"""Tests for GemmailMessage.from_bytes_b() — Misfin(B) format parser."""

import pytest

from titlani.content.gemmail import GemmailMessage


class TestBFormatSenderLines:
    def test_single_sender_no_blurb(self):
        data = b"< alice@example.com\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.senders) == 1
        assert msg.senders[0].mailbox == "alice"
        assert msg.senders[0].hostname == "example.com"
        assert msg.senders[0].blurb == ""

    def test_single_sender_with_blurb(self):
        data = b"< alice@example.com Alice Smith\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders[0].blurb == "Alice Smith"

    def test_multiple_sender_lines_for_forwarding(self):
        data = (
            b"< list@lists.com Mailing List\n"
            b"< original@sender.com Original Author\n"
            b"Body content.\n"
        )
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.senders) == 2
        assert msg.senders[0].mailbox == "list"
        assert msg.senders[1].mailbox == "original"

    def test_sender_lines_stripped_from_body(self):
        data = b"< alice@example.com\nActual body.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert "< alice" not in msg.body
        assert "Actual body." in msg.body

    def test_malformed_sender_kept_in_body(self):
        data = b"< not-an-address\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders == []
        assert "< not-an-address" in msg.body


class TestBFormatRecipientLine:
    def test_single_recipient(self):
        data = b": bob@example.com\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.recipients) == 1
        assert msg.recipients[0].mailbox == "bob"

    def test_multiple_recipients_space_separated(self):
        data = b": alice@a.com bob@b.com carol@c.com\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.recipients) == 3
        assert msg.recipients[0].mailbox == "alice"
        assert msg.recipients[1].mailbox == "bob"
        assert msg.recipients[2].mailbox == "carol"

    def test_only_first_recipient_line_used(self):
        data = b": alice@a.com\n: bob@b.com\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.recipients) == 1
        assert msg.recipients[0].mailbox == "alice"
        assert ": bob@b.com" in msg.body

    def test_recipient_line_stripped_from_body(self):
        data = b": bob@example.com\nReal body.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert ": bob" not in msg.body

    def test_malformed_recipient_tokens_skipped(self):
        data = b": alice@a.com not-valid bob@b.com\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.recipients) == 2


class TestBFormatTimestampLine:
    def test_valid_timestamp(self):
        data = b"@ 2023-05-09T19:39:15Z\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.timestamps) == 1
        assert msg.timestamps[0].year == 2023
        assert msg.timestamps[0].month == 5

    def test_only_first_timestamp_used(self):
        data = b"@ 2023-01-01T00:00:00Z\n@ 2023-02-01T00:00:00Z\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.timestamps) == 1
        assert msg.timestamps[0].month == 1
        assert "@ 2023-02-01" in msg.body

    def test_malformed_timestamp_kept_in_body(self):
        data = b"@ not-a-timestamp\n@ 2023-05-09T19:39:15Z\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        # First @ line is consumed (malformed), second stays in body
        assert msg.timestamps == []
        assert "@ not-a-timestamp" in msg.body
        assert "@ 2023-05-09" in msg.body

    def test_timestamp_line_stripped_from_body(self):
        data = b"@ 2023-05-09T19:39:15Z\nReal body.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert "@ 2023" not in msg.body


class TestBFormatFullMessage:
    def test_all_metadata_types(self):
        data = (
            b"< alice@example.com Alice\n"
            b": bob@example.com\n"
            b"@ 2023-05-09T19:39:15Z\n"
            b"# Hello\n"
            b"\n"
            b"Message body.\n"
        )
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders[0].address == "alice@example.com"
        assert msg.senders[0].blurb == "Alice"
        assert msg.recipients[0].address == "bob@example.com"
        assert msg.timestamps[0].year == 2023
        assert msg.body == "# Hello\n\nMessage body.\n"

    def test_metadata_anywhere_in_body(self):
        data = (
            b"# Subject\n"
            b"\n"
            b"Intro paragraph.\n"
            b"< alice@example.com\n"
            b": bob@mail.com\n"
            b"@ 2023-05-09T19:39:15Z\n"
            b"Rest of body.\n"
        )
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders[0].mailbox == "alice"
        assert msg.body == "# Subject\n\nIntro paragraph.\nRest of body.\n"

    def test_no_metadata_at_all(self):
        data = b"Just a plain gemtext message.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders == []
        assert msg.recipients == []
        assert msg.timestamps == []
        assert msg.body == "Just a plain gemtext message.\n"

    def test_empty_body_after_metadata(self):
        data = b"< alice@example.com\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders[0].mailbox == "alice"
        assert msg.body == ""

    def test_subject_extraction(self):
        data = b"< alice@example.com\n# My Subject\nBody.\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.subject == "My Subject"

    def test_crlf_line_endings(self):
        data = b"< alice@example.com\r\n: bob@mail.com\r\nBody.\r\n"
        msg = GemmailMessage.from_bytes_b(data)
        assert msg.senders[0].mailbox == "alice"
        assert msg.recipients[0].mailbox == "bob"

    def test_bare_cr_rejected(self):
        data = b"< alice@example.com\rBody.\n"
        with pytest.raises(ValueError, match="CR must only appear"):
            GemmailMessage.from_bytes_b(data)

    def test_invalid_utf8_rejected(self):
        with pytest.raises(ValueError, match="not valid UTF-8"):
            GemmailMessage.from_bytes_b(b"\xff\xfe< alice@example.com\n")


class TestBFormatForwarding:
    def test_forwarded_message_preserves_sender_chain(self):
        data = (
            b"< list@lists.example.com Mailing List\n"
            b"< author@sender.example.com Original Author\n"
            b": subscriber@reader.example.com\n"
            b"@ 2023-05-09T19:39:15Z\n"
            b"# Original Post\n"
            b"\n"
            b"The original message body.\n"
        )
        msg = GemmailMessage.from_bytes_b(data)
        assert len(msg.senders) == 2
        assert msg.senders[0].mailbox == "list"
        assert msg.senders[1].mailbox == "author"
        assert "< list" not in msg.body
        assert "< author" not in msg.body
        assert "The original message body." in msg.body
