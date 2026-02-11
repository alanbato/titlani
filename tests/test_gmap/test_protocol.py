"""Tests for GeminiServerProtocol."""

from unittest.mock import AsyncMock, MagicMock

from titlani.gmap.handler import GeminiResponse
from titlani.gmap.protocol import GeminiServerProtocol


def make_protocol(handler=None):
    """Create a protocol with a mock handler and transport."""
    if handler is None:
        handler = AsyncMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"OK")
        )
    protocol = GeminiServerProtocol(request_handler=handler)
    transport = MagicMock()
    transport.get_extra_info.return_value = ("127.0.0.1", 12345)
    transport.is_closing.return_value = False
    protocol.connection_made(transport)
    return protocol, transport, handler


class TestGeminiServerProtocol:
    def test_connection_made(self):
        protocol, transport, _ = make_protocol()
        assert protocol.transport is transport
        assert protocol.peer_name == ("127.0.0.1", 12345)

    def test_request_too_large(self):
        protocol, transport, _ = make_protocol()
        protocol.data_received(b"x" * 1025)
        transport.write.assert_called_once()
        written = transport.write.call_args[0][0]
        assert b"59" in written  # BAD_REQUEST

    def test_parse_valid_request(self):
        handler = MagicMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"")
        )
        protocol, transport, _ = make_protocol(handler)
        protocol.data_received(b"gemini://example.com/tag/Inbox\r\n")

        handler.assert_called_once()
        req = handler.call_args[0][0]
        assert req.hostname == "example.com"
        assert req.path == "/tag/Inbox"

    def test_parse_with_query(self):
        handler = MagicMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"")
        )
        protocol, transport, _ = make_protocol(handler)
        protocol.data_received(b"gemini://example.com/tag/Archive?20260211T120000Z\r\n")

        handler.assert_called_once()
        req = handler.call_args[0][0]
        assert req.path == "/tag/Archive"
        assert req.query == "20260211T120000Z"

    def test_invalid_request(self):
        protocol, transport, _ = make_protocol()
        protocol.data_received(b"not-a-url\r\n")
        transport.write.assert_called_once()
        written = transport.write.call_args[0][0]
        assert b"59" in written

    def test_incremental_data(self):
        handler = MagicMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"")
        )
        protocol, transport, _ = make_protocol(handler)
        protocol.data_received(b"gemini://example")
        handler.assert_not_called()

        protocol.data_received(b".com/tag/Inbox\r\n")
        handler.assert_called_once()

    def test_response_written(self):
        handler = MagicMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"hello")
        )
        protocol, transport, _ = make_protocol(handler)
        protocol.data_received(b"gemini://example.com/tag/\r\n")

        transport.write.assert_called_once()
        written = transport.write.call_args[0][0]
        assert written == b"20 text/plain\r\nhello"

    def test_connection_lost_cleans_up(self):
        protocol, transport, _ = make_protocol()
        protocol.connection_lost(None)
        assert protocol.transport is None
