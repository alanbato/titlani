"""Tests for MisfinRequest."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from titlani.protocol.constants import MAX_CONTENT_LENGTH, MAX_HEADER_SIZE
from titlani.protocol.request import MisfinRequest


class TestMisfinRequestFromHeader:
    def test_valid_header(self):
        header = b"misfin://alice@example.com\t128"
        req = MisfinRequest.from_header(header)
        assert req.mailbox == "alice"
        assert req.hostname == "example.com"
        assert req.content_length == 128

    def test_zero_content_length(self):
        header = b"misfin://alice@example.com\t0"
        req = MisfinRequest.from_header(header)
        assert req.content_length == 0

    def test_max_content_length(self):
        header = f"misfin://alice@example.com\t{MAX_CONTENT_LENGTH}".encode()
        req = MisfinRequest.from_header(header)
        assert req.content_length == MAX_CONTENT_LENGTH

    def test_missing_tab(self):
        with pytest.raises(ValueError, match="Missing TAB"):
            MisfinRequest.from_header(b"misfin://alice@example.com 128")

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="Invalid scheme"):
            MisfinRequest.from_header(b"gemini://alice@example.com\t128")

    def test_missing_at_sign(self):
        with pytest.raises(ValueError, match="Invalid address"):
            MisfinRequest.from_header(b"misfin://example.com\t128")

    def test_empty_mailbox(self):
        with pytest.raises(ValueError, match="Invalid address"):
            MisfinRequest.from_header(b"misfin://@example.com\t128")

    def test_empty_hostname(self):
        with pytest.raises(ValueError, match="Invalid address"):
            MisfinRequest.from_header(b"misfin://alice@\t128")

    def test_invalid_content_length(self):
        with pytest.raises(ValueError, match="Invalid content length"):
            MisfinRequest.from_header(b"misfin://alice@example.com\tabc")

    def test_negative_content_length(self):
        with pytest.raises(ValueError, match="non-negative"):
            MisfinRequest.from_header(b"misfin://alice@example.com\t-1")

    def test_exceeds_max_content_length(self):
        too_big = MAX_CONTENT_LENGTH + 1
        with pytest.raises(ValueError, match="exceeds maximum"):
            MisfinRequest.from_header(
                f"misfin://alice@example.com\t{too_big}".encode()
            )

    def test_oversized_header(self):
        long_mailbox = "a" * 1000
        header = f"misfin://{long_mailbox}@example.com\t128".encode()
        with pytest.raises(ValueError, match="exceeds maximum size"):
            MisfinRequest.from_header(header)

    def test_invalid_utf8(self):
        with pytest.raises(ValueError, match="Invalid UTF-8"):
            MisfinRequest.from_header(b"misfin://\xff@example.com\t128")


class TestMisfinRequestToBytes:
    def test_to_bytes(self):
        req = MisfinRequest(
            mailbox="alice",
            hostname="example.com",
            content_length=5,
            raw_message=b"hello",
        )
        result = req.to_bytes()
        assert result == b"misfin://alice@example.com\t5\r\nhello"

    def test_to_bytes_roundtrip(self):
        original = b"misfin://bob@mail.test\t12"
        req = MisfinRequest.from_header(original)
        req.raw_message = b"test message"
        result = req.to_bytes()
        # Parse back the header part
        header_part = result.split(b"\r\n", 1)[0]
        req2 = MisfinRequest.from_header(header_part)
        assert req2.mailbox == req.mailbox
        assert req2.hostname == req.hostname
        assert req2.content_length == req.content_length


class TestMisfinRequestParseMessage:
    def test_parse_message(self, sample_message_bytes):
        req = MisfinRequest(
            mailbox="recipient",
            hostname="test.example.com",
            content_length=len(sample_message_bytes),
            raw_message=sample_message_bytes,
        )
        msg = req.parse_message()
        assert len(msg.senders) == 1
        assert msg.senders[0].mailbox == "sender"
        assert msg.body.startswith("# Hello")


class TestMisfinRequestHypothesis:
    @given(
        mailbox=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
            ),
            min_size=1,
            max_size=50,
        ),
        hostname=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters=".",
            ),
            min_size=1,
            max_size=50,
        ),
        content_length=st.integers(min_value=0, max_value=MAX_CONTENT_LENGTH),
    )
    def test_roundtrip(self, mailbox, hostname, content_length):
        # Skip if header would be too long
        header = f"misfin://{mailbox}@{hostname}\t{content_length}"
        if len(header.encode("utf-8")) > MAX_HEADER_SIZE:
            return

        req = MisfinRequest.from_header(header.encode("utf-8"))
        assert req.mailbox == mailbox
        assert req.hostname == hostname
        assert req.content_length == content_length
