"""Misfin(C) client protocol implementation using asyncio.Protocol."""

import asyncio

from cryptography import x509

from ..protocol.constants import CRLF, MAX_RESPONSE_SIZE
from ..protocol.response import MisfinResponse


class MisfinClientProtocol(asyncio.Protocol):
    def __init__(
        self,
        request_bytes: bytes,
        response_future: asyncio.Future,
    ) -> None:
        self.request_bytes = request_bytes
        self.response_future = response_future
        self.transport: asyncio.Transport | None = None
        self.buffer = b""
        self.header_received = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        if self.transport:
            self.transport.write(self.request_bytes)

    def data_received(self, data: bytes) -> None:
        self.buffer += data

        if not self.header_received and CRLF in self.buffer:
            header_line, _ = self.buffer.split(CRLF, 1)
            self.header_received = True

            try:
                response = MisfinResponse.from_line(header_line.decode("utf-8"))
                if not self.response_future.done():
                    self.response_future.set_result(response)
            except (ValueError, UnicodeDecodeError) as e:
                if not self.response_future.done():
                    self.response_future.set_exception(e)

            if self.transport:
                self.transport.close()

        # DoS protection
        if len(self.buffer) > MAX_RESPONSE_SIZE:
            if not self.response_future.done():
                self.response_future.set_exception(
                    ValueError("Response exceeds maximum size")
                )
            if self.transport:
                self.transport.close()

    def eof_received(self) -> bool:
        return False

    def connection_lost(self, exc: Exception | None) -> None:
        if self.response_future.done():
            return
        if exc:
            self.response_future.set_exception(exc)
            return
        if not self.header_received:
            self.response_future.set_exception(
                ConnectionError("Connection closed before receiving response")
            )

    def get_peer_certificate(self) -> x509.Certificate | None:
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
