"""Tests for ProtocolDispatcher."""

from unittest.mock import AsyncMock, MagicMock

from titlani.gmap.handler import GeminiResponse
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode
from titlani.server.dispatcher import ProtocolDispatcher


def make_dispatcher(misfin_handler=None, gmap_handler=None):
    if misfin_handler is None:
        misfin_handler = AsyncMock(
            return_value=MisfinResponse(status=StatusCode.SUCCESS, meta="fp")
        )
    if gmap_handler is None:
        gmap_handler = AsyncMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"")
        )
    dispatcher = ProtocolDispatcher(
        misfin_handler=misfin_handler,
        gmap_handler=gmap_handler,
    )
    transport = MagicMock()
    transport.get_extra_info.return_value = ("127.0.0.1", 12345)
    transport.is_closing.return_value = False
    dispatcher.connection_made(transport)
    return dispatcher, transport, misfin_handler, gmap_handler


class TestProtocolDispatcher:
    def test_detect_misfin(self):
        dispatcher, transport, misfin_handler, gmap_handler = make_dispatcher()
        dispatcher.data_received(b"misfin://alice@example.com\t0\r\n")

        assert dispatcher.delegate is not None
        assert "Misfin" in type(dispatcher.delegate).__name__

    def test_detect_gemini(self):
        dispatcher, transport, misfin_handler, gmap_handler = make_dispatcher()
        dispatcher.data_received(b"gemini://example.com/tag/Inbox\r\n")

        assert dispatcher.delegate is not None
        assert "Gemini" in type(dispatcher.delegate).__name__

    def test_unknown_defaults_to_misfin(self):
        dispatcher, transport, _, _ = make_dispatcher()
        dispatcher.data_received(b"something://unknown\r\n")

        assert dispatcher.delegate is not None
        assert "Misfin" in type(dispatcher.delegate).__name__

    def test_incremental_detection(self):
        dispatcher, transport, _, _ = make_dispatcher()
        # Send only 5 bytes — not enough to detect
        dispatcher.data_received(b"misf")
        assert dispatcher.delegate is None

        # Send enough to detect
        dispatcher.data_received(b"in://alice@example.com\t0\r\n")
        assert dispatcher.delegate is not None

    def test_connection_lost_forwarded(self):
        dispatcher, transport, _, _ = make_dispatcher()
        dispatcher.data_received(b"gemini://example.com/tag/\r\n")
        delegate = dispatcher.delegate
        assert delegate is not None

        dispatcher.connection_lost(None)
        # Should not raise

    def test_data_forwarded_after_detection(self):
        handler = MagicMock(
            return_value=GeminiResponse(status=20, meta="text/plain", body=b"")
        )
        dispatcher, transport, _, _ = make_dispatcher(gmap_handler=handler)
        dispatcher.data_received(b"gemini://example.com/tag/\r\n")

        # Verify the handler was called
        handler.assert_called_once()
