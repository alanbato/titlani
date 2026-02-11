"""Gemini server protocol for GMAP.

Single-phase buffering: accumulate data until CRLF, parse the Gemini
request URL, extract client cert, delegate to handler.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from cryptography import x509
from tlacacoca import get_logger

from ..protocol.constants import CRLF, REQUEST_TIMEOUT
from .handler import (
    BAD_REQUEST,
    MAX_GEMINI_REQUEST_SIZE,
    GeminiRequest,
    GeminiResponse,
    parse_gemini_request,
)

logger = get_logger(__name__)


class GeminiServerProtocol(asyncio.Protocol):
    """Gemini protocol handler for GMAP requests.

    Simpler than MisfinServerProtocol: single-phase (no body),
    accumulate until CRLF, parse URL, route to handler.
    """

    def __init__(
        self,
        request_handler: Callable[
            [GeminiRequest],
            GeminiResponse | Awaitable[GeminiResponse],
        ],
    ) -> None:
        self.request_handler = request_handler
        self.transport: asyncio.Transport | None = None
        self.buffer = b""
        self.peer_name: tuple[str, int] | None = None
        self.request_start_time: float | None = None
        self.timeout_handle: asyncio.TimerHandle | None = None
        self.received_first_byte = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        if self.transport:
            self.peer_name = self.transport.get_extra_info("peername")
        self.request_start_time = time.time()

        try:
            loop = asyncio.get_running_loop()
            self.timeout_handle = loop.call_later(REQUEST_TIMEOUT, self._handle_timeout)
        except RuntimeError:
            self.timeout_handle = None

        logger.debug(
            "gmap_connection_established",
            client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
        )

    def data_received(self, data: bytes) -> None:
        self.received_first_byte = True
        self.buffer += data

        if len(self.buffer) > MAX_GEMINI_REQUEST_SIZE and CRLF not in self.buffer:
            logger.warning(
                "gmap_request_too_large",
                client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
                buffer_size=len(self.buffer),
            )
            self._send_error(
                BAD_REQUEST,
                f"Request exceeds {MAX_GEMINI_REQUEST_SIZE} bytes",
            )
            return

        if CRLF not in self.buffer:
            return

        self._cancel_timeout()

        request_line, _ = self.buffer.split(CRLF, 1)

        client_cert = self._get_peer_certificate()

        try:
            request = parse_gemini_request(request_line, client_cert)
        except ValueError as e:
            self._send_error(BAD_REQUEST, str(e))
            return

        logger.debug(
            "gmap_request_parsed",
            client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
            path=request.path,
            query=request.query,
        )

        self._process_request(request)

    def _process_request(self, request: GeminiRequest) -> None:
        try:
            result = self.request_handler(request)
            if isinstance(result, GeminiResponse):
                self._send_response(result)
                return
            try:
                task = asyncio.ensure_future(result)
                task.add_done_callback(lambda t: self._handle_result(t))
            except RuntimeError:
                self._send_error(40, "Server error")
        except Exception as e:
            logger.error(
                "gmap_handler_error",
                client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
                error=str(e),
            )
            self._send_error(40, f"Server error: {e}")

    def _handle_result(self, task: asyncio.Task) -> None:
        try:
            response = task.result()
            self._send_response(response)
        except Exception as e:
            logger.error(
                "gmap_handler_error",
                client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
                error=str(e),
            )
            self._send_error(40, f"Server error: {e}")

    def _send_response(self, response: GeminiResponse) -> None:
        if not self.transport:
            return

        duration_ms = 0.0
        if self.request_start_time:
            duration_ms = (time.time() - self.request_start_time) * 1000

        logger.info(
            "gmap_request_completed",
            client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
            status=response.status,
            duration_ms=round(duration_ms, 2),
        )

        self.transport.write(response.to_bytes())
        self.transport.close()

    def _send_error(self, status: int, message: str) -> None:
        self._send_response(GeminiResponse(status=status, meta=message))

    def _handle_timeout(self) -> None:
        if self.transport and not self.transport.is_closing():
            logger.warning(
                "gmap_request_timeout",
                client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
            )
            if self.received_first_byte:
                response = GeminiResponse(status=BAD_REQUEST, meta="Request timeout")
                self.transport.write(response.to_bytes())
            self.transport.close()

    def _cancel_timeout(self) -> None:
        if self.timeout_handle:
            self.timeout_handle.cancel()
            self.timeout_handle = None

    def connection_lost(self, exc: Exception | None) -> None:
        self._cancel_timeout()
        logger.debug(
            "gmap_connection_lost",
            client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
            error=str(exc) if exc else None,
        )
        self.transport = None

    def _get_peer_certificate(self) -> x509.Certificate | None:
        if self.transport is None:
            return None
        ssl_object = self.transport.get_extra_info("ssl_object")
        if ssl_object is None:
            return None
        try:
            der_cert = ssl_object.getpeercert(binary_form=True)
            if der_cert:
                return x509.load_der_x509_certificate(der_cert)
        except Exception:
            return None
        return None
