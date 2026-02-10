"""Misfin(C) server protocol implementation using asyncio.Protocol.

Two-phase buffering state machine:
1. AWAITING_HEADER: accumulate until CRLF, parse with MisfinRequest.from_header()
2. AWAITING_BODY: accumulate until content_length bytes received
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from cryptography import x509
from tlacacoca import (
    DenialReason,
    MiddlewareChain,
    MiddlewareResult,
    get_certificate_fingerprint,
    get_logger,
)

from ..identity.certificate import normalize_fingerprint
from ..protocol.constants import (
    CRLF,
    MAX_B_REQUEST_SIZE,
    MAX_HEADER_SIZE,
    REQUEST_TIMEOUT,
)
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode

logger = get_logger(__name__)

# Map DenialReason -> Misfin status codes
_DENIAL_STATUS_MAP: dict[str, StatusCode] = {
    DenialReason.RATE_LIMIT: StatusCode.SLOW_DOWN,
    DenialReason.ACCESS_DENIED: StatusCode.DOMAIN_NOT_SERVICED,
    DenialReason.CERT_REQUIRED: StatusCode.CERTIFICATE_REQUIRED,
    DenialReason.CERT_NOT_AUTHORIZED: StatusCode.UNAUTHORIZED_SENDER,
}


class MisfinServerProtocol(asyncio.Protocol):
    def __init__(
        self,
        message_handler: Callable[
            [MisfinRequest],
            MisfinResponse | Awaitable[MisfinResponse],
        ],
        middleware: MiddlewareChain | None = None,
    ) -> None:
        self.message_handler = message_handler
        self.middleware = middleware
        self.transport: asyncio.Transport | None = None
        self.buffer = b""
        self.peer_name: tuple[str, int] | None = None
        self.request_start_time: float | None = None
        self.timeout_handle: asyncio.TimerHandle | None = None

        # Two-phase state
        self.request: MisfinRequest | None = None
        self.header_received = False
        self.awaiting_body = False
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
            "connection_established",
            client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
        )

    def data_received(self, data: bytes) -> None:
        self.received_first_byte = True
        self.buffer += data

        if not self.header_received:
            self._receive_header()
            return

        # Phase 2: Waiting for message body
        if self.awaiting_body and self.request:
            if len(self.buffer) >= self.request.content_length:
                self._cancel_timeout()
                self.request.raw_message = self.buffer[: self.request.content_length]
                self._process_request()

    def _receive_header(self) -> None:
        """Phase 1: Accumulate until CRLF, parse header."""
        # DoS protection: use max of C and B sizes
        dos_limit = max(MAX_HEADER_SIZE, MAX_B_REQUEST_SIZE)
        if len(self.buffer) > dos_limit and CRLF not in self.buffer:
            self._send_error(
                StatusCode.BAD_REQUEST,
                f"Header exceeds maximum size ({dos_limit} bytes)",
            )
            return

        if CRLF not in self.buffer:
            return

        header_line, remaining = self.buffer.split(CRLF, 1)
        self.buffer = remaining
        self.header_received = True

        try:
            self.request = MisfinRequest.from_header(header_line)
        except ValueError:
            # If no TAB in header, try Misfin(B) format
            if b"\t" not in header_line:
                try:
                    self.request = MisfinRequest.from_header_b(header_line)
                except ValueError as e2:
                    self._send_error(StatusCode.BAD_REQUEST, str(e2))
                    return
            else:
                self._send_error(
                    StatusCode.BAD_REQUEST,
                    "Invalid request header",
                )
                return

        # Attach client cert info
        client_cert = self._get_peer_certificate()
        if client_cert:
            self.request.client_cert = client_cert
            raw_fp = get_certificate_fingerprint(client_cert)
            self.request.client_cert_fingerprint = normalize_fingerprint(raw_fp)

        # B requests have no body phase
        if self.request.protocol_version == "B" or self.request.content_length == 0:
            self._cancel_timeout()
            self._process_request()
            return

        self.awaiting_body = True

        # Check if body already in buffer
        if len(self.buffer) >= self.request.content_length:
            self._cancel_timeout()
            self.request.raw_message = self.buffer[: self.request.content_length]
            self._process_request()

    def _process_request(self) -> None:
        if not self.request:
            return

        client_ip = self.peer_name[0] if self.peer_name else "unknown"

        # Process through middleware if present
        if self.middleware:
            try:
                request_url = f"misfin://{self.request.mailbox}@{self.request.hostname}"
                task = asyncio.create_task(
                    self.middleware.process_request(
                        request_url,
                        client_ip,
                        self.request.client_cert_fingerprint,
                    )
                )
                task.add_done_callback(
                    lambda t: self._handle_middleware_result(t, client_ip)
                )
                return
            except RuntimeError:
                logger.warning(
                    "middleware_skipped",
                    client_ip=client_ip,
                    reason="no_event_loop",
                )

        self._route_request(client_ip)

    def _handle_middleware_result(self, task: asyncio.Task, client_ip: str) -> None:
        try:
            result: MiddlewareResult = task.result()
            if not result.allowed:
                status = _DENIAL_STATUS_MAP.get(
                    result.denial_reason or "",
                    StatusCode.TEMPORARY_FAILURE,
                )
                meta = f"{status.name.replace('_', ' ').title()}"
                if result.retry_after and status == StatusCode.SLOW_DOWN:
                    meta += f". Retry after {result.retry_after}s"
                self._send_error(status, meta)
                return
            self._route_request(client_ip)
        except Exception as e:
            logger.error(
                "middleware_error",
                client_ip=client_ip,
                error=str(e),
            )
            self._send_error(StatusCode.TEMPORARY_FAILURE, "Middleware error")

    def _route_request(self, client_ip: str) -> None:
        if not self.request:
            return

        try:
            result = self.message_handler(self.request)
            if isinstance(result, MisfinResponse):
                self._send_response(result)
                return
            try:
                task = asyncio.ensure_future(result)
                task.add_done_callback(
                    lambda t: self._handle_handler_result(t, client_ip)
                )
                return
            except RuntimeError:
                self._send_error(
                    StatusCode.TEMPORARY_FAILURE,
                    "Server error",
                )
                return
        except Exception as e:
            logger.error(
                "handler_error",
                client_ip=client_ip,
                error=str(e),
            )
            self._send_error(
                StatusCode.TEMPORARY_FAILURE,
                f"Server error: {e}",
            )

    def _handle_handler_result(self, task: asyncio.Task, client_ip: str) -> None:
        try:
            response = task.result()
            self._send_response(response)
        except Exception as e:
            logger.error(
                "handler_error",
                client_ip=client_ip,
                error=str(e),
            )
            self._send_error(
                StatusCode.TEMPORARY_FAILURE,
                f"Server error: {e}",
            )

    def _send_response(self, response: MisfinResponse) -> None:
        if not self.transport:
            return

        duration_ms = 0.0
        if self.request_start_time:
            duration_ms = (time.time() - self.request_start_time) * 1000

        logger.info(
            "request_completed",
            client_ip=(self.peer_name[0] if self.peer_name else "unknown"),
            status=response.status,
            duration_ms=round(duration_ms, 2),
        )

        self.transport.write(response.to_bytes())
        self.transport.close()

    def _send_error(self, status: StatusCode, message: str) -> None:
        response = MisfinResponse(status=status.value, meta=message)
        self._send_response(response)

    def _handle_timeout(self) -> None:
        if self.transport and not self.transport.is_closing():
            # Per spec: don't send data until receiving at least one byte
            if self.received_first_byte:
                response = MisfinResponse(
                    status=StatusCode.BAD_REQUEST,
                    meta="Request timeout",
                )
                self.transport.write(response.to_bytes())
            self.transport.close()

    def _cancel_timeout(self) -> None:
        if self.timeout_handle:
            self.timeout_handle.cancel()
            self.timeout_handle = None

    def connection_lost(self, exc: Exception | None) -> None:
        self._cancel_timeout()
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
