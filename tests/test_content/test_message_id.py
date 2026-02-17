"""Tests for message ID generation and threading utilities."""

from datetime import UTC, datetime

from titlani.content.message_id import (
    build_reply_link,
    extract_reply_to_ids,
    generate_message_id,
    parse_message_id_from_filename,
)


class TestGenerateMessageId:
    def test_returns_8_hex_chars(self):
        ts = datetime(2026, 2, 13, 14, 30, 52, tzinfo=UTC)
        result = generate_message_id("alice@example.com", ts)
        assert len(result) == 8
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        ts = datetime(2026, 2, 13, 14, 30, 52, tzinfo=UTC)
        a = generate_message_id("alice@example.com", ts)
        b = generate_message_id("alice@example.com", ts)
        assert a == b

    def test_different_sender_different_id(self):
        ts = datetime(2026, 2, 13, 14, 30, 52, tzinfo=UTC)
        a = generate_message_id("alice@example.com", ts)
        b = generate_message_id("bob@example.com", ts)
        assert a != b

    def test_different_timestamp_different_id(self):
        t1 = datetime(2026, 2, 13, 14, 30, 52, tzinfo=UTC)
        t2 = datetime(2026, 2, 13, 14, 30, 53, tzinfo=UTC)
        a = generate_message_id("alice@example.com", t1)
        b = generate_message_id("alice@example.com", t2)
        assert a != b

    def test_empty_sender(self):
        ts = datetime(2026, 2, 13, 14, 30, 52, tzinfo=UTC)
        result = generate_message_id("", ts)
        assert len(result) == 8


class TestParseMessageIdFromFilename:
    def test_new_format_plain(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z-a1b2c3d4.gemmail")
            == "20260213T143052Z-a1b2c3d4"
        )

    def test_new_format_new(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z-a1b2c3d4.gemmail.new")
            == "20260213T143052Z-a1b2c3d4"
        )

    def test_new_format_enc(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z-a1b2c3d4.gemmail.enc")
            == "20260213T143052Z-a1b2c3d4"
        )

    def test_new_format_enc_new(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z-a1b2c3d4.gemmail.enc.new")
            == "20260213T143052Z-a1b2c3d4"
        )

    def test_old_format_plain(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z.gemmail")
            == "20260213T143052Z"
        )

    def test_old_format_new(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z.gemmail.new")
            == "20260213T143052Z"
        )

    def test_old_format_enc(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z.gemmail.enc")
            == "20260213T143052Z"
        )

    def test_old_format_enc_new(self):
        assert (
            parse_message_id_from_filename("20260213T143052Z.gemmail.enc.new")
            == "20260213T143052Z"
        )

    def test_invalid_extension(self):
        assert parse_message_id_from_filename("20260213T143052Z.txt") is None

    def test_invalid_stem(self):
        assert parse_message_id_from_filename("invalid.gemmail") is None

    def test_no_extension(self):
        assert parse_message_id_from_filename("20260213T143052Z") is None


class TestExtractReplyToIds:
    def test_single_reply_link(self):
        body = "# Re: Hello\n\nThanks!\n=> mid:20260213T143052Z-a1b2c3d4 In reply to\n"
        assert extract_reply_to_ids(body) == ["20260213T143052Z-a1b2c3d4"]

    def test_multiple_reply_links(self):
        body = (
            "# Re: Thread\n\n"
            "=> mid:20260213T143052Z-a1b2c3d4 In reply to\n"
            "=> mid:20260212T100000Z-deadbeef In reply to\n"
        )
        result = extract_reply_to_ids(body)
        assert result == [
            "20260213T143052Z-a1b2c3d4",
            "20260212T100000Z-deadbeef",
        ]

    def test_no_reply_links(self):
        body = "# Hello\n\nJust a regular message.\n"
        assert extract_reply_to_ids(body) == []

    def test_old_format_msgid(self):
        body = "=> mid:20260213T143052Z In reply to\n"
        assert extract_reply_to_ids(body) == ["20260213T143052Z"]

    def test_ignores_non_mid_links(self):
        body = "=> gemini://example.com Some link\n=> mid:abc123 In reply to\n"
        assert extract_reply_to_ids(body) == ["abc123"]


class TestBuildReplyLink:
    def test_format(self):
        result = build_reply_link("20260213T143052Z-a1b2c3d4")
        assert result == "=> mid:20260213T143052Z-a1b2c3d4 In reply to"

    def test_old_format_msgid(self):
        result = build_reply_link("20260213T143052Z")
        assert result == "=> mid:20260213T143052Z In reply to"
