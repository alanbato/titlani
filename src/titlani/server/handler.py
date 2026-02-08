"""Message handlers for the Misfin server."""

import abc
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..identity.certificate import normalize_fingerprint
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode


class MessageHandler(abc.ABC):
    @abc.abstractmethod
    async def handle_message(self, request: MisfinRequest) -> MisfinResponse: ...


class FileMailboxHandler(MessageHandler):
    """Stores messages as .gemmail files in mailbox_dir/<mailbox>/."""

    def __init__(
        self,
        mailbox_dir: Path,
        hostname: str,
        recipient_fingerprint_fn: Callable[[str], str | None] | None = None,
        identity_cert_fingerprint: str = "",
    ) -> None:
        self.mailbox_dir = mailbox_dir
        self.hostname = hostname
        self.recipient_fingerprint_fn = recipient_fingerprint_fn
        self.identity_cert_fingerprint = identity_cert_fingerprint

    async def handle_message(self, request: MisfinRequest) -> MisfinResponse:
        if request.hostname != self.hostname:
            return MisfinResponse(
                status=StatusCode.DOMAIN_NOT_SERVICED,
                meta="Domain not serviced by this server",
            )

        # Verification probes: zero-length messages get a fingerprint response
        if request.content_length == 0:
            return MisfinResponse(
                status=StatusCode.SUCCESS,
                meta=self.identity_cert_fingerprint,
            )

        # Sanitize mailbox name to prevent path traversal
        mailbox = request.mailbox
        if (
            not mailbox
            or "\x00" in mailbox
            or "/" in mailbox
            or "\\" in mailbox
            or ".." in mailbox
            or not re.fullmatch(r"[a-zA-Z0-9._-]+", mailbox)
        ):
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Invalid mailbox name",
            )

        mailbox_path = self.mailbox_dir / mailbox

        # Verify resolved path is inside mailbox_dir (symlink-safe)
        try:
            resolved = mailbox_path.resolve(strict=False)
            mailbox_dir_resolved = self.mailbox_dir.resolve(strict=False)
            if not str(resolved).startswith(
                str(mailbox_dir_resolved) + os.sep
            ):
                return MisfinResponse(
                    status=StatusCode.BAD_REQUEST,
                    meta="Invalid mailbox name",
                )
        except (OSError, ValueError):
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Invalid mailbox name",
            )

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
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{timestamp}.gemmail"
        filepath = mailbox_path / filename
        filepath.write_bytes(request.raw_message)
        os.chmod(filepath, 0o600)

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
