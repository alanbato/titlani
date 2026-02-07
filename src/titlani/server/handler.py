"""Message handlers for the Misfin server."""

import abc
from datetime import UTC, datetime
from pathlib import Path

from ..identity.certificate import normalize_fingerprint
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode


class MessageHandler(abc.ABC):
    @abc.abstractmethod
    async def handle_message(
        self, request: MisfinRequest
    ) -> MisfinResponse:
        ...


class FileMailboxHandler(MessageHandler):
    """Stores messages as .gemmail files in mailbox_dir/<mailbox>/."""

    def __init__(
        self,
        mailbox_dir: Path,
        hostname: str,
        recipient_fingerprint_fn: "callable | None" = None,
    ) -> None:
        self.mailbox_dir = mailbox_dir
        self.hostname = hostname
        self.recipient_fingerprint_fn = recipient_fingerprint_fn

    async def handle_message(
        self, request: MisfinRequest
    ) -> MisfinResponse:
        if request.hostname != self.hostname:
            return MisfinResponse(
                status=StatusCode.DOMAIN_NOT_SERVICED,
                meta="Domain not serviced by this server",
            )

        mailbox_path = self.mailbox_dir / request.mailbox
        if not mailbox_path.is_dir():
            return MisfinResponse(
                status=StatusCode.MAILBOX_NOT_FOUND,
                meta="Mailbox does not exist",
            )

        # Validate message format
        try:
            request.parse_message()
        except ValueError:
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Invalid message format",
            )

        # Store message
        timestamp = datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        filename = f"{timestamp}.gemmail"
        filepath = mailbox_path / filename
        filepath.write_bytes(request.raw_message)

        # Get recipient fingerprint
        fingerprint = ""
        if self.recipient_fingerprint_fn:
            raw_fp = self.recipient_fingerprint_fn(request.mailbox)
            if raw_fp:
                fingerprint = normalize_fingerprint(raw_fp)

        return MisfinResponse(
            status=StatusCode.SUCCESS,
            meta=fingerprint,
        )
