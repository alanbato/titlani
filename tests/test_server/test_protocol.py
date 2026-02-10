"""Tests for MisfinServerProtocol."""

from unittest.mock import AsyncMock, MagicMock

from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode
from titlani.server.protocol import MisfinServerProtocol


def make_protocol(handler=None):
    """Create a protocol with a mock handler and transport."""
    if handler is None:
        handler = AsyncMock(
            return_value=MisfinResponse(status=StatusCode.SUCCESS, meta="fingerprint")
        )
    protocol = MisfinServerProtocol(message_handler=handler)
    transport = MagicMock()
    transport.get_extra_info.return_value = ("127.0.0.1", 12345)
    transport.is_closing.return_value = False
    # Don't trigger the event loop timeout
    protocol.connection_made(transport)
    return protocol, transport, handler


class TestMisfinServerProtocol:
    def test_connection_made(self):
        protocol, transport, _ = make_protocol()
        assert protocol.transport is transport
        assert protocol.peer_name == ("127.0.0.1", 12345)

    def test_header_too_long(self):
        protocol, transport, _ = make_protocol()
        # Send data larger than DoS limit (max of C and B sizes) without CRLF
        protocol.data_received(b"x" * 2049)
        # Should send error response
        transport.write.assert_called_once()
        written = transport.write.call_args[0][0]
        assert b"59" in written  # BAD_REQUEST

    def test_parse_valid_header(self):
        handler = MagicMock(
            return_value=MisfinResponse(status=StatusCode.SUCCESS, meta="fp")
        )
        protocol, transport, _ = make_protocol(handler)

        # Send header + body for zero-length message
        protocol.data_received(b"misfin://alice@example.com\t0\r\n")

        assert protocol.header_received is True
        assert protocol.request is not None
        assert protocol.request.mailbox == "alice"
        assert protocol.request.hostname == "example.com"
        assert protocol.request.content_length == 0

    def test_two_phase_body_reception(self):
        handler = MagicMock(
            return_value=MisfinResponse(status=StatusCode.SUCCESS, meta="fp")
        )
        protocol, transport, _ = make_protocol(handler)

        # Phase 1: Header
        protocol.data_received(b"misfin://alice@example.com\t5\r\n")
        assert protocol.header_received is True
        assert protocol.awaiting_body is True

        # Phase 2: Body (partial)
        protocol.data_received(b"hel")
        # Not enough data yet
        assert protocol.request.raw_message == b""

        # Phase 2: Body (complete)
        protocol.data_received(b"lo")
        assert protocol.request.raw_message == b"hello"

    def test_body_in_same_packet_as_header(self):
        handler = MagicMock(
            return_value=MisfinResponse(status=StatusCode.SUCCESS, meta="fp")
        )
        protocol, transport, _ = make_protocol(handler)

        # Send header + body in one packet
        protocol.data_received(b"misfin://alice@example.com\t5\r\nhello")
        assert protocol.request.raw_message == b"hello"

    def test_invalid_header_sends_bad_request(self):
        protocol, transport, _ = make_protocol()

        protocol.data_received(b"invalid header\r\n")
        transport.write.assert_called_once()
        written = transport.write.call_args[0][0]
        assert b"59" in written  # BAD_REQUEST

    def test_connection_lost_cleans_up(self):
        protocol, transport, _ = make_protocol()
        protocol.connection_lost(None)
        assert protocol.transport is None

    def test_timeout_with_no_data(self):
        protocol, transport, _ = make_protocol()
        # Simulate timeout without receiving any data
        protocol._handle_timeout()
        # Should close without sending (per spec: no data until byte received)
        transport.close.assert_called_once()
        transport.write.assert_not_called()

    def test_timeout_after_partial_data(self):
        protocol, transport, _ = make_protocol()
        # Simulate receiving some data then timeout
        protocol.received_first_byte = True
        protocol._handle_timeout()
        # Should send bad request then close
        transport.write.assert_called_once()
        written = transport.write.call_args[0][0]
        assert b"59" in written  # BAD_REQUEST
        transport.close.assert_called_once()
