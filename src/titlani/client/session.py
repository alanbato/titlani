"""High-level Misfin client API with TOFU support."""

import asyncio
import re
import ssl
from datetime import UTC, datetime
from pathlib import Path

from tlacacoca import (
    CertificateChangedError,
    TOFUDatabase,
    create_client_context,
    get_certificate_fingerprint,
    get_logger,
)

from ..content.gemmail import GemmailMessage, MisfinAddress
from ..protocol.constants import DEFAULT_PORT, MAX_REDIRECTS, REQUEST_TIMEOUT
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode, is_redirect
from .protocol import MisfinClientProtocol

logger = get_logger(__name__)

_RETRY_DELAY_RE = re.compile(r"(\d+)\s*s")


class MisfinClient:
    def __init__(
        self,
        timeout: float = REQUEST_TIMEOUT,
        port: int = DEFAULT_PORT,
        ssl_context: ssl.SSLContext | None = None,
        trust_on_first_use: bool = True,
        tofu_db_path: Path | None = None,
        client_cert: Path | str | None = None,
        client_key: Path | str | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        misfin_b_fallback: bool = True,
    ) -> None:
        self.timeout = timeout
        self.port = port
        self.trust_on_first_use = trust_on_first_use
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.misfin_b_fallback = misfin_b_fallback

        if client_cert and not client_key:
            raise ValueError("client_key is required when client_cert is provided")
        if client_key and not client_cert:
            raise ValueError("client_cert is required when client_key is provided")

        if self.trust_on_first_use:
            self.tofu_db: TOFUDatabase | None = TOFUDatabase(tofu_db_path)
        else:
            self.tofu_db = None

        if ssl_context is None:
            self.ssl_context = create_client_context(
                verify_mode=ssl.CERT_NONE,
                check_hostname=False,
                certfile=(str(client_cert) if client_cert else None),
                keyfile=(str(client_key) if client_key else None),
            )
        else:
            self.ssl_context = ssl_context

    async def __aenter__(self) -> "MisfinClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.tofu_db = None

    async def send(
        self,
        to: str,
        body: str,
        subject: str | None = None,
        sender: MisfinAddress | None = None,
        recipients: list[MisfinAddress] | None = None,
    ) -> MisfinResponse:
        """Send a message to a Misfin address.

        Args:
            to: Recipient address in "mailbox@hostname" format.
            body: Message body in gemtext format.
            subject: Optional subject (prepended as # heading).
            sender: Optional sender address.
            recipients: Optional list of recipient addresses.
        """
        if "@" not in to:
            raise ValueError(f"Invalid address: {to!r}")

        mailbox, hostname = to.rsplit("@", 1)
        recipient = MisfinAddress(mailbox=mailbox, hostname=hostname)

        # Build message body
        full_body = ""
        if subject:
            full_body = f"# {subject}\n\n"
        full_body += body
        if not full_body.endswith("\n"):
            full_body += "\n"

        message = GemmailMessage(
            senders=[sender] if sender else [],
            recipients=recipients or [recipient],
            timestamps=[datetime.now(UTC)],
            body=full_body,
        )

        logger.debug("client_send", to=to)
        message_bytes = message.to_bytes()
        return await self.send_raw(to, message_bytes)

    async def send_raw(
        self,
        to: str,
        message_bytes: bytes,
        _redirect_depth: int = 0,
    ) -> MisfinResponse:
        """Send pre-formatted message bytes."""
        if "@" not in to:
            raise ValueError(f"Invalid address: {to!r}")

        mailbox, hostname = to.rsplit("@", 1)

        request = MisfinRequest(
            mailbox=mailbox,
            hostname=hostname,
            content_length=len(message_bytes),
            raw_message=message_bytes,
        )

        return await self._send_request(request, hostname, _redirect_depth)

    _B_FALLBACK_STATUSES = {
        StatusCode.BAD_REQUEST,
        StatusCode.TEMPORARY_FAILURE,
        StatusCode.CERTIFICATE_REQUIRED,
    }

    async def _send_request(
        self,
        request: MisfinRequest,
        hostname: str,
        redirect_depth: int = 0,
    ) -> MisfinResponse:
        response = await self._send_request_once(request, hostname)

        retries = 0
        while response.status == StatusCode.SLOW_DOWN and retries < self.max_retries:
            delay = self._parse_retry_delay(response.meta)
            logger.warning(
                "client_slow_down_retry",
                hostname=hostname,
                attempt=retries + 1,
                delay=delay,
            )
            await asyncio.sleep(delay)
            response = await self._send_request_once(request, hostname)
            retries += 1

        if response.status == StatusCode.SLOW_DOWN and retries >= self.max_retries:
            logger.warning(
                "client_max_retries_exceeded",
                hostname=hostname,
                retries=retries,
            )

        # Handle redirects
        if is_redirect(response.status):
            redirect_addr = response.redirect_address
            if redirect_addr:
                if redirect_depth >= MAX_REDIRECTS:
                    logger.warning(
                        "client_redirect_max_depth",
                        hostname=hostname,
                        depth=redirect_depth,
                    )
                    return MisfinResponse(
                        status=StatusCode.PERMANENT_FAILURE,
                        meta="Too many redirects",
                    )
                logger.info(
                    "client_redirect_following",
                    target=redirect_addr,
                )
                return await self.send_raw(
                    redirect_addr,
                    request.raw_message,
                    _redirect_depth=redirect_depth + 1,
                )

        # Misfin(B) fallback
        if (
            self.misfin_b_fallback
            and request.protocol_version == "C"
            and response.status in self._B_FALLBACK_STATUSES
        ):
            logger.info(
                "client_b_fallback",
                hostname=hostname,
                original_status=response.status,
            )
            return await self._send_request_b(request, hostname)

        return response

    async def _send_request_b(
        self, request: MisfinRequest, hostname: str
    ) -> MisfinResponse:
        try:
            b_bytes = request.to_bytes_b()
        except ValueError:
            logger.warning(
                "client_b_message_too_large",
                hostname=hostname,
            )
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Message too large for Misfin(B) format",
            )

        loop = asyncio.get_running_loop()
        response_future: asyncio.Future = loop.create_future()
        protocol = MisfinClientProtocol(b_bytes, response_future)

        try:
            transport, protocol = await asyncio.wait_for(
                loop.create_connection(
                    lambda: protocol,
                    host=hostname,
                    port=self.port,
                    ssl=self.ssl_context,
                    server_hostname=hostname,
                ),
                timeout=self.timeout,
            )
        except (TimeoutError, OSError):
            logger.warning(
                "client_b_connection_failed",
                hostname=hostname,
            )
            return MisfinResponse(
                status=StatusCode.TEMPORARY_FAILURE,
                meta="Misfin(B) fallback connection failed",
            )

        try:
            response: MisfinResponse = await asyncio.wait_for(
                response_future, timeout=self.timeout
            )
            return response
        except TimeoutError:
            logger.warning(
                "client_b_timeout",
                hostname=hostname,
            )
            return MisfinResponse(
                status=StatusCode.TEMPORARY_FAILURE,
                meta="Misfin(B) fallback timed out",
            )
        finally:
            transport.close()

    def _parse_retry_delay(self, meta: str) -> float:
        match = _RETRY_DELAY_RE.search(meta)
        if match:
            return float(match.group(1))
        return self.retry_base_delay

    async def _send_request_once(
        self, request: MisfinRequest, hostname: str
    ) -> MisfinResponse:
        loop = asyncio.get_running_loop()
        response_future: asyncio.Future = loop.create_future()

        request_bytes = request.to_bytes()
        protocol = MisfinClientProtocol(request_bytes, response_future)

        try:
            transport, protocol = await asyncio.wait_for(
                loop.create_connection(
                    lambda: protocol,
                    host=hostname,
                    port=self.port,
                    ssl=self.ssl_context,
                    server_hostname=hostname,
                ),
                timeout=self.timeout,
            )
        except TimeoutError as e:
            raise TimeoutError(f"Connection timeout: {hostname}") from e
        except OSError as e:
            raise ConnectionError(f"Connection failed: {e}") from e

        try:
            # TOFU verification
            if self.tofu_db:
                cert = protocol.get_peer_certificate()
                if cert:
                    is_valid, message = self.tofu_db.verify(hostname, self.port, cert)
                    if not is_valid and message == "changed":
                        old_info = self.tofu_db.get_host_info(hostname, self.port)
                        old_fp = old_info["fingerprint"] if old_info else "unknown"
                        new_fp = get_certificate_fingerprint(cert)
                        logger.warning(
                            "client_tofu_cert_changed",
                            hostname=hostname,
                            old_fingerprint=old_fp[:16] + "...",
                            new_fingerprint=new_fp[:16] + "...",
                        )
                        raise CertificateChangedError(
                            hostname,
                            self.port,
                            old_fp,
                            new_fp,
                        )
                    elif message == "first_use":
                        fp = get_certificate_fingerprint(cert)
                        logger.info(
                            "client_tofu_first_use",
                            hostname=hostname,
                            fingerprint=fp[:16] + "...",
                        )
                        self.tofu_db.trust(hostname, self.port, cert)
                else:
                    logger.warning(
                        "client_no_peer_cert",
                        hostname=hostname,
                    )

            response: MisfinResponse = await asyncio.wait_for(
                response_future, timeout=self.timeout
            )
            logger.debug(
                "client_response_received",
                hostname=hostname,
                status=response.status,
            )
            return response
        except TimeoutError as e:
            raise TimeoutError(f"Request timeout: {hostname}") from e
        finally:
            transport.close()
