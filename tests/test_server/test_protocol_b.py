"""Tests for Misfin(B) server-side detection and handling."""

from unittest.mock import AsyncMock, MagicMock

from titlani.protocol.status import StatusCode
from titlani.server.protocol import MisfinServerProtocol


def _make_protocol(handler=None, middleware=None):
    if handler is None:
        handler = AsyncMock()
    proto = MisfinServerProtocol(message_handler=handler, middleware=middleware)
    transport = MagicMock()
    transport.get_extra_info.return_value = ("127.0.0.1", 12345)
    transport.is_closing.return_value = False
    proto.connection_made(transport)
    return proto, transport, handler


class TestMisfinBDetection:
    def test_b_format_detected_without_tab(self):
        handler = AsyncMock()
        from titlani.protocol.response import MisfinResponse

        handler.return_value = MisfinResponse(status=StatusCode.SUCCESS, meta="ok")
        proto, transport, _ = _make_protocol(handler=handler)

        proto.data_received(b"misfin://alice@example.com Hello world\r\n")

        handler.assert_called_once()
        request = handler.call_args[0][0]
        assert request.protocol_version == "B"
        assert request.mailbox == "alice"
        assert request.hostname == "example.com"
        assert request.raw_message == b"Hello world"

    def test_c_format_still_works(self):
        handler = AsyncMock()
        from titlani.protocol.response import MisfinResponse

        handler.return_value = MisfinResponse(status=StatusCode.SUCCESS, meta="ok")
        proto, transport, _ = _make_protocol(handler=handler)

        body = b"sender@host\nrecipient@host\n2024-01-01T00:00:00Z\nHello\n"
        header = f"misfin://alice@example.com\t{len(body)}\r\n"
        proto.data_received(header.encode() + body)

        handler.assert_called_once()
        request = handler.call_args[0][0]
        assert request.protocol_version == "C"

    def test_b_format_no_body_phase(self):
        handler = AsyncMock()
        from titlani.protocol.response import MisfinResponse

        handler.return_value = MisfinResponse(status=StatusCode.SUCCESS, meta="ok")
        proto, transport, _ = _make_protocol(handler=handler)

        proto.data_received(b"misfin://alice@example.com Hello\r\n")

        # Handler is called immediately, no awaiting_body phase
        assert not proto.awaiting_body
        handler.assert_called_once()

    def test_invalid_b_format_sends_bad_request(self):
        proto, transport, _ = _make_protocol()

        # No tab, no space after address -> both C and B fail
        proto.data_received(b"misfin://alice@example.com\r\n")

        written = transport.write.call_args[0][0]
        assert b"59" in written

    def test_invalid_header_with_tab_sends_bad_request(self):
        proto, transport, _ = _make_protocol()

        # Has tab but invalid C format (bad content length)
        proto.data_received(b"misfin://alice@example.com\tnot_a_number\r\n")

        written = transport.write.call_args[0][0]
        assert b"59" in written
