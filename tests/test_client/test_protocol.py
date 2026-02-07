"""Tests for MisfinClientProtocol."""

import asyncio
from unittest.mock import MagicMock

import pytest

from titlani.client.protocol import MisfinClientProtocol


class TestMisfinClientProtocol:
    def test_sends_request_on_connection(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        request_bytes = b"misfin://alice@example.com\t5\r\nhello"
        protocol = MisfinClientProtocol(request_bytes, future)

        transport = MagicMock()
        protocol.connection_made(transport)

        transport.write.assert_called_once_with(request_bytes)
        loop.close()

    def test_parses_success_response(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        protocol = MisfinClientProtocol(b"test", future)

        transport = MagicMock()
        protocol.connection_made(transport)

        protocol.data_received(b"20 abc123\r\n")

        assert future.done()
        response = future.result()
        assert response.status == 20
        assert response.meta == "abc123"
        loop.close()

    def test_parses_error_response(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        protocol = MisfinClientProtocol(b"test", future)

        transport = MagicMock()
        protocol.connection_made(transport)

        protocol.data_received(b"51 Mailbox not found\r\n")

        assert future.done()
        response = future.result()
        assert response.status == 51
        loop.close()

    def test_connection_lost_before_response(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        protocol = MisfinClientProtocol(b"test", future)

        transport = MagicMock()
        protocol.connection_made(transport)
        protocol.connection_lost(None)

        assert future.done()
        with pytest.raises(ConnectionError):
            future.result()
        loop.close()

    def test_connection_lost_with_exception(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        protocol = MisfinClientProtocol(b"test", future)

        transport = MagicMock()
        protocol.connection_made(transport)
        protocol.connection_lost(OSError("connection reset"))

        assert future.done()
        with pytest.raises(OSError):
            future.result()
        loop.close()

    def test_eof_received_returns_false(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        protocol = MisfinClientProtocol(b"test", future)
        assert protocol.eof_received() is False
        loop.close()
