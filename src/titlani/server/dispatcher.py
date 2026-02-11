"""Multi-protocol dispatcher for Misfin and GMAP on a shared port.

Detects protocol type from the first bytes of the request:
- 'misfin://' -> delegate to MisfinServerProtocol
- 'gemini://' -> delegate to GeminiServerProtocol
"""

import asyncio
from collections.abc import Awaitable, Callable

from tlacacoca import MiddlewareChain, get_logger

from ..gmap.handler import GeminiRequest, GeminiResponse
from ..gmap.protocol import GeminiServerProtocol
from ..protocol.constants import REQUEST_TIMEOUT
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from .protocol import MisfinServerProtocol as MisfinProtocol

logger = get_logger(__name__)

MISFIN_PREFIX = b"misfin://"
GEMINI_PREFIX = b"gemini://"
# Need at most 9 bytes to distinguish protocols
DETECT_SIZE = max(len(MISFIN_PREFIX), len(GEMINI_PREFIX))


class ProtocolDispatcher(asyncio.Protocol):
    """Dispatches connections to Misfin or GMAP based on first bytes."""

    def __init__(
        self,
        misfin_handler: Callable[
            [MisfinRequest],
            MisfinResponse | Awaitable[MisfinResponse],
        ],
        gmap_handler: Callable[
            [GeminiRequest],
            GeminiResponse | Awaitable[GeminiResponse],
        ],
        middleware: MiddlewareChain | None = None,
    ) -> None:
        self.misfin_handler = misfin_handler
        self.gmap_handler = gmap_handler
        self.middleware = middleware
        self.transport: asyncio.Transport | None = None
        self.buffer = b""
        self.delegate: asyncio.Protocol | None = None
        self.timeout_handle: asyncio.TimerHandle | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        try:
            loop = asyncio.get_running_loop()
            self.timeout_handle = loop.call_later(REQUEST_TIMEOUT, self._handle_timeout)
        except RuntimeError:
            self.timeout_handle = None

    def data_received(self, data: bytes) -> None:
        if self.delegate is not None:
            self.delegate.data_received(data)
            return

        self.buffer += data

        if len(self.buffer) < DETECT_SIZE:
            return

        self._detect_and_delegate()

    def _detect_and_delegate(self) -> None:
        if self.transport is None:
            return

        self._cancel_timeout()

        if self.buffer.startswith(GEMINI_PREFIX):
            logger.debug("protocol_detected", protocol="gmap")
            self.delegate = GeminiServerProtocol(
                request_handler=self.gmap_handler,
            )
        elif self.buffer.startswith(MISFIN_PREFIX):
            logger.debug("protocol_detected", protocol="misfin")
            self.delegate = MisfinProtocol(
                message_handler=self.misfin_handler,
                middleware=self.middleware,
            )
        else:
            # Default to Misfin for backwards compatibility
            logger.debug(
                "protocol_detected",
                protocol="misfin_default",
            )
            self.delegate = MisfinProtocol(
                message_handler=self.misfin_handler,
                middleware=self.middleware,
            )

        # Forward the transport and buffered data
        self.delegate.connection_made(self.transport)
        if self.buffer:
            self.delegate.data_received(self.buffer)
            self.buffer = b""

    def _handle_timeout(self) -> None:
        if self.transport and not self.transport.is_closing():
            if self.delegate is None:
                logger.warning(
                    "dispatcher_timeout",
                    buffer_size=len(self.buffer),
                )
                self.transport.close()

    def _cancel_timeout(self) -> None:
        if self.timeout_handle:
            self.timeout_handle.cancel()
            self.timeout_handle = None

    def connection_lost(self, exc: Exception | None) -> None:
        self._cancel_timeout()
        if self.delegate is not None:
            self.delegate.connection_lost(exc)
        self.transport = None
