"""High-level Misfin client API with TOFU support."""

import asyncio
import ssl
from datetime import UTC, datetime
from pathlib import Path

from tlacacoca import (
    CertificateChangedError,
    TOFUDatabase,
    create_client_context,
    get_certificate_fingerprint,
)

from ..content.gemmail import GemmailMessage, MisfinAddress
from ..protocol.constants import DEFAULT_PORT, REQUEST_TIMEOUT
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import is_redirect
from .protocol import MisfinClientProtocol


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
    ) -> None:
        self.timeout = timeout
        self.port = port
        self.trust_on_first_use = trust_on_first_use

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
        pass

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

        message_bytes = message.to_bytes()
        return await self.send_raw(to, message_bytes)

    async def send_raw(self, to: str, message_bytes: bytes) -> MisfinResponse:
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

        return await self._send_request(request, hostname)

    async def _send_request(
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
                        raise CertificateChangedError(
                            hostname,
                            self.port,
                            old_fp,
                            new_fp,
                        )
                    elif message == "first_use":
                        self.tofu_db.trust(hostname, self.port, cert)

            response: MisfinResponse = await asyncio.wait_for(
                response_future, timeout=self.timeout
            )

            # Handle redirects
            if is_redirect(response.status):
                redirect_addr = response.redirect_address
                if redirect_addr:
                    return await self.send_raw(redirect_addr, request.raw_message)

            return response
        except TimeoutError as e:
            raise TimeoutError(f"Request timeout: {hostname}") from e
        finally:
            transport.close()
