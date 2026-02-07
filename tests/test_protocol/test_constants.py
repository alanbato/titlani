"""Tests for protocol constants."""

from titlani.protocol.constants import (
    CRLF,
    DEFAULT_PORT,
    LF,
    MAX_CONTENT_LENGTH,
    MAX_HEADER_SIZE,
    MAX_METADATA_LINE_SIZE,
    MAX_RESPONSE_SIZE,
    MISFIN_SCHEME,
    REQUEST_TIMEOUT,
    SPACE,
    TAB,
)


class TestConstants:
    def test_default_port(self):
        assert DEFAULT_PORT == 1958

    def test_max_sizes(self):
        assert MAX_HEADER_SIZE == 1024
        assert MAX_CONTENT_LENGTH == 16384
        assert MAX_METADATA_LINE_SIZE == 1024
        assert MAX_RESPONSE_SIZE == 2048

    def test_bytes_constants(self):
        assert CRLF == b"\r\n"
        assert LF == b"\n"
        assert TAB == b"\t"
        assert SPACE == b" "

    def test_scheme(self):
        assert MISFIN_SCHEME == "misfin"

    def test_timeout(self):
        assert REQUEST_TIMEOUT == 30.0
