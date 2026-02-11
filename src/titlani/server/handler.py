"""Message handlers for the Misfin server."""

import abc
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tlacacoca import get_logger

from ..content.gemmail import GemmailMessage, MisfinAddress
from ..encryption.manager import EncryptionManager
from ..identity.certificate import extract_identity, normalize_fingerprint
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode

logger = get_logger(__name__)


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
        encryption_manager: EncryptionManager | None = None,
    ) -> None:
        self.mailbox_dir = mailbox_dir
        self.hostname = hostname
        self.recipient_fingerprint_fn = recipient_fingerprint_fn
        self.identity_cert_fingerprint = identity_cert_fingerprint
        self.encryption_manager = encryption_manager

    async def handle_message(self, request: MisfinRequest) -> MisfinResponse:
        if request.hostname != self.hostname:
            logger.info(
                "domain_not_serviced",
                requested_hostname=request.hostname,
                server_hostname=self.hostname,
                mailbox=request.mailbox,
            )
            return MisfinResponse(
                status=StatusCode.DOMAIN_NOT_SERVICED,
                meta="Domain not serviced by this server",
            )

        # Verification probes: zero-length messages get a fingerprint response
        if request.content_length == 0:
            logger.debug(
                "verification_probe_received",
                mailbox=request.mailbox,
                hostname=request.hostname,
            )
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
            logger.warning(
                "invalid_mailbox_name",
                mailbox=repr(mailbox),
                hostname=request.hostname,
            )
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Invalid mailbox name",
            )

        mailbox_path = self.mailbox_dir / mailbox

        # Verify resolved path is inside mailbox_dir (symlink-safe)
        try:
            resolved = mailbox_path.resolve(strict=False)
            mailbox_dir_resolved = self.mailbox_dir.resolve(strict=False)
            if not str(resolved).startswith(str(mailbox_dir_resolved) + os.sep):
                logger.warning(
                    "path_traversal_blocked",
                    mailbox=mailbox,
                    resolved_path=str(resolved),
                    mailbox_dir=str(mailbox_dir_resolved),
                )
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
            logger.info(
                "mailbox_not_found",
                mailbox=mailbox,
                hostname=request.hostname,
            )
            return MisfinResponse(
                status=StatusCode.MAILBOX_NOT_FOUND,
                meta="Mailbox does not exist",
            )

        # Validate and prepare message for storage
        message_bytes = self._prepare_message(request)
        if message_bytes is None:
            logger.info(
                "message_format_invalid",
                mailbox=mailbox,
                hostname=request.hostname,
                content_length=request.content_length,
            )
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Invalid message format",
            )

        self._store_message(mailbox, mailbox_path, message_bytes)

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

    @staticmethod
    def _extract_sender(request: MisfinRequest) -> MisfinAddress | None:
        """Extract sender identity from client certificate if available."""
        if request.client_cert is None:
            return None
        try:
            identity = extract_identity(request.client_cert)
            if identity.mailbox and identity.hostname:
                return MisfinAddress(
                    mailbox=identity.mailbox,
                    hostname=identity.hostname,
                    blurb=identity.blurb,
                )
        except Exception:
            pass
        return None

    def _prepare_message(self, request: MisfinRequest) -> bytes | None:
        now = datetime.now(UTC)
        sender = self._extract_sender(request)

        if request.protocol_version == "B":
            body_text = request.raw_message.decode("utf-8")
            if not body_text.endswith("\n"):
                body_text += "\n"
            recipient = MisfinAddress(
                mailbox=request.mailbox,
                hostname=request.hostname,
            )
            senders = [sender] if sender else []
            envelope = GemmailMessage(
                senders=senders,
                recipients=[recipient],
                timestamps=[now],
                body=body_text,
            )
            return envelope.to_bytes()

        try:
            msg = request.parse_message()
        except ValueError:
            return None

        # Prepend server timestamp and sender identity per spec
        msg.timestamps.insert(0, now)
        if sender:
            msg.senders.insert(0, sender)

        return msg.to_bytes()

    def _store_message(self, mailbox: str, mailbox_path: Path, data: bytes) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if self.encryption_manager and self.encryption_manager.has_key(mailbox):
            filename = f"{timestamp}.gemmail.enc"
            filepath = mailbox_path / filename
            encrypted = self.encryption_manager.encrypt(mailbox, data)
            filepath.write_bytes(encrypted)
            is_encrypted = True
        else:
            filename = f"{timestamp}.gemmail"
            filepath = mailbox_path / filename
            filepath.write_bytes(data)
            is_encrypted = False
        os.chmod(filepath, 0o600)
        logger.info(
            "message_delivered",
            mailbox=mailbox,
            file=filename,
            encrypted=is_encrypted,
        )
