"""Tests for MisfinResponse."""

import pytest

from titlani.protocol.response import MisfinResponse


class TestMisfinResponse:
    def test_from_line_success(self):
        resp = MisfinResponse.from_line("20 abc123def456")
        assert resp.status == 20
        assert resp.meta == "abc123def456"

    def test_from_line_error(self):
        resp = MisfinResponse.from_line("51 Mailbox not found")
        assert resp.status == 51
        assert resp.meta == "Mailbox not found"

    def test_from_line_no_meta(self):
        resp = MisfinResponse.from_line("40")
        assert resp.status == 40
        assert resp.meta == ""

    def test_from_line_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid status code"):
            MisfinResponse.from_line("xx bad")

    def test_from_line_empty(self):
        with pytest.raises(ValueError):
            MisfinResponse.from_line("")

    def test_to_bytes(self):
        resp = MisfinResponse(status=20, meta="fingerprint123")
        assert resp.to_bytes() == b"20 fingerprint123\r\n"

    def test_to_bytes_roundtrip(self):
        resp = MisfinResponse(status=30, meta="user@other.com")
        line = resp.to_bytes().decode().rstrip("\r\n")
        parsed = MisfinResponse.from_line(line)
        assert parsed.status == resp.status
        assert parsed.meta == resp.meta

    def test_fingerprint_success(self):
        resp = MisfinResponse(status=20, meta="abc123")
        assert resp.fingerprint == "abc123"

    def test_fingerprint_non_success(self):
        resp = MisfinResponse(status=51, meta="abc123")
        assert resp.fingerprint is None

    def test_fingerprint_empty_meta(self):
        resp = MisfinResponse(status=20, meta="")
        assert resp.fingerprint is None

    def test_redirect_address(self):
        resp = MisfinResponse(status=30, meta="user@other.com")
        assert resp.redirect_address == "user@other.com"

    def test_redirect_address_non_redirect(self):
        resp = MisfinResponse(status=20, meta="user@other.com")
        assert resp.redirect_address is None

    def test_frozen(self):
        resp = MisfinResponse(status=20, meta="test")
        with pytest.raises(AttributeError):
            resp.status = 50  # type: ignore[misc]
