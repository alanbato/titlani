"""Tests for Misfin(B) request format parsing and serialization."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from titlani.protocol.constants import MAX_B_REQUEST_SIZE
from titlani.protocol.request import MisfinRequest


class TestFromHeaderB:
    def test_valid_b_request(self):
        header = b"misfin://alice@example.com Hello there"
        req = MisfinRequest.from_header_b(header)
        assert req.mailbox == "alice"
        assert req.hostname == "example.com"
        assert req.raw_message == b"Hello there"
        assert req.content_length == len(b"Hello there")
        assert req.protocol_version == "B"

    def test_message_with_spaces(self):
        header = b"misfin://alice@example.com Hello world how are you"
        req = MisfinRequest.from_header_b(header)
        assert req.raw_message == b"Hello world how are you"

    def test_unicode_message(self):
        msg = "Hola amigo"
        header = f"misfin://alice@example.com {msg}".encode()
        req = MisfinRequest.from_header_b(header)
        assert req.raw_message.decode("utf-8") == msg

    def test_oversized_request_raises(self):
        msg = "x" * MAX_B_REQUEST_SIZE
        header = f"misfin://a@b.com {msg}".encode()
        with pytest.raises(ValueError, match="exceeds maximum size"):
            MisfinRequest.from_header_b(header)

    def test_missing_space_raises(self):
        header = b"misfin://alice@example.com"
        with pytest.raises(ValueError, match="Missing space"):
            MisfinRequest.from_header_b(header)

    def test_empty_message_raises(self):
        header = b"misfin://alice@example.com "
        with pytest.raises(ValueError, match="Empty message"):
            MisfinRequest.from_header_b(header)

    def test_invalid_scheme_raises(self):
        header = b"gemini://alice@example.com Hello"
        with pytest.raises(ValueError, match="Invalid scheme"):
            MisfinRequest.from_header_b(header)

    def test_no_at_in_address_raises(self):
        header = b"misfin://example.com Hello"
        with pytest.raises(ValueError, match="Invalid address"):
            MisfinRequest.from_header_b(header)

    def test_empty_mailbox_raises(self):
        header = b"misfin://@example.com Hello"
        with pytest.raises(ValueError, match="Invalid address"):
            MisfinRequest.from_header_b(header)


class TestToBytesB:
    def test_simple_message(self):
        req = MisfinRequest(
            mailbox="alice",
            hostname="example.com",
            content_length=5,
            raw_message=b"Hello",
        )
        result = req.to_bytes_b()
        assert result == b"misfin://alice@example.com Hello\r\n"

    def test_strips_gemmail_metadata(self):
        gemmail = (
            b"sender@host.com\nalice@example.com\n2024-01-01T00:00:00Z\nHello world\n"
        )
        req = MisfinRequest(
            mailbox="alice",
            hostname="example.com",
            content_length=len(gemmail),
            raw_message=gemmail,
        )
        result = req.to_bytes_b()
        assert result == b"misfin://alice@example.com Hello world\r\n"

    def test_oversized_raises(self):
        msg = ("x" * MAX_B_REQUEST_SIZE).encode("utf-8")
        req = MisfinRequest(
            mailbox="alice",
            hostname="example.com",
            content_length=len(msg),
            raw_message=msg,
        )
        with pytest.raises(ValueError, match="exceeds maximum size"):
            req.to_bytes_b()


class TestBRoundtrip:
    @given(
        mailbox=st.from_regex(r"[a-zA-Z][a-zA-Z0-9._-]{0,19}", fullmatch=True),
        hostname=st.from_regex(r"[a-z][a-z0-9]{0,10}\.[a-z]{2,4}", fullmatch=True),
        message=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\r\n\t",
            ),
        ),
    )
    @settings(max_examples=50)
    def test_roundtrip(self, mailbox, hostname, message):
        header = f"misfin://{mailbox}@{hostname} {message}"
        header_bytes = header.encode("utf-8")
        if len(header_bytes) > MAX_B_REQUEST_SIZE:
            return  # Skip oversized
        req = MisfinRequest.from_header_b(header_bytes)
        assert req.mailbox == mailbox
        assert req.hostname == hostname
        assert req.raw_message == message.encode("utf-8")
        assert req.protocol_version == "B"
