"""Message handlers for the Misfin server."""

import abc
import asyncio
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tlacacoca import get_logger

from ..content.gemmail import GemmailMessage, MisfinAddress
from ..encryption.manager import EncryptionManager
from ..identity.certificate import extract_identity, normalize_fingerprint
from ..protocol.constants import DEFAULT_PORT
from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode
from .lists import (
    get_or_create_list_identity,
    is_mailing_list,
    is_subscriber,
    load_subscribers,
    should_prevent_loop,
)

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
        auto_reply_enabled: bool = False,
        auto_reply_interval: int = 86400,
        identity_certfile: Path | None = None,
        identity_keyfile: Path | None = None,
        port: int = DEFAULT_PORT,
        lists_enabled: bool = False,
        lists_archive: bool = True,
    ) -> None:
        self.mailbox_dir = mailbox_dir
        self.hostname = hostname
        self.recipient_fingerprint_fn = recipient_fingerprint_fn
        self.identity_cert_fingerprint = identity_cert_fingerprint
        self.encryption_manager = encryption_manager
        self.auto_reply_enabled = auto_reply_enabled
        self.auto_reply_interval = auto_reply_interval
        self.identity_certfile = identity_certfile
        self.identity_keyfile = identity_keyfile
        self.port = port
        self.lists_enabled = lists_enabled
        self.lists_archive = lists_archive
        self._auto_reply_last_sent: dict[str, datetime] = {}

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

        result = self._validate_mailbox(request)
        if isinstance(result, MisfinResponse):
            return result
        mailbox, mailbox_path = result

        # Check sender against block list
        senders = self._collect_senders(request)
        blocked_sender = self._find_blocked_sender(mailbox_path, senders)
        if blocked_sender is not None:
            logger.info(
                "sender_blocked",
                mailbox=mailbox,
                sender=blocked_sender.address,
            )
            return MisfinResponse(
                status=StatusCode.UNAUTHORIZED_SENDER,
                meta="Sender blocked",
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

        # Mailing list posting restriction: reject non-subscribers and loops
        list_rejection = self._check_list_posting(
            mailbox, mailbox_path, senders, message_bytes
        )
        if list_rejection is not None:
            return list_rejection

        is_list = self._is_active_list(mailbox_path)
        should_store = not is_list or self.lists_archive
        if should_store:
            self._store_message(mailbox, mailbox_path, message_bytes)
        self._maybe_trigger_auto_reply(mailbox, mailbox_path, message_bytes)
        self._maybe_trigger_list_forwarding(mailbox, mailbox_path, message_bytes)

        return MisfinResponse(
            status=StatusCode.SUCCESS,
            meta=self._get_recipient_fingerprint(request.mailbox),
        )

    def _validate_mailbox(
        self, request: MisfinRequest
    ) -> tuple[str, Path] | MisfinResponse:
        """Validate mailbox name and resolve path.

        Returns (mailbox, mailbox_path) on success, or MisfinResponse on error.
        """
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

        return (mailbox, mailbox_path)

    def _maybe_trigger_auto_reply(
        self,
        mailbox: str,
        mailbox_path: Path,
        message_bytes: bytes,
    ) -> None:
        """Trigger auto-reply if configured and appropriate."""
        if not self.auto_reply_enabled:
            return
        try:
            parsed_msg = GemmailMessage.from_bytes(message_bytes)
            if self._should_auto_reply(mailbox_path, parsed_msg):
                asyncio.ensure_future(
                    self._send_auto_reply(mailbox, mailbox_path, parsed_msg)
                )
        except Exception:
            pass  # Never let auto-reply affect delivery

    def _get_recipient_fingerprint(self, mailbox: str) -> str:
        """Get the normalized fingerprint for a mailbox recipient."""
        if self.recipient_fingerprint_fn:
            raw_fp = self.recipient_fingerprint_fn(mailbox)
            if raw_fp:
                return normalize_fingerprint(raw_fp)
        return ""

    def _collect_senders(self, request: MisfinRequest) -> list[MisfinAddress]:
        """Gather sender addresses from client cert and message metadata."""
        senders: list[MisfinAddress] = []
        cert_sender = self._extract_sender(request)
        if cert_sender:
            senders.append(cert_sender)
        # For Misfin(C), also parse senders from gemmail metadata
        if request.protocol_version == "C" and request.raw_message:
            try:
                msg = request.parse_message()
                senders.extend(msg.senders)
            except (ValueError, Exception):
                pass
        return senders

    @staticmethod
    def _find_blocked_sender(
        mailbox_path: Path, senders: list[MisfinAddress]
    ) -> MisfinAddress | None:
        """Return the first blocked sender, or None if none are blocked."""
        if not senders:
            return None
        blocked_file = mailbox_path / ".blocked"
        if not blocked_file.exists():
            return None
        try:
            lines = blocked_file.read_text().strip().splitlines()
            blocked = {line.strip().lower() for line in lines if line.strip()}
        except (OSError, UnicodeDecodeError):
            logger.warning(
                "blocked_list_read_failed",
                mailbox_path=str(mailbox_path),
            )
            return None
        for sender in senders:
            if sender.address.lower() in blocked:
                return sender
        return None

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
        from ..content.message_id import generate_message_id

        timestamp = datetime.now(UTC)
        timestamp_str = timestamp.strftime("%Y%m%dT%H%M%SZ")

        # Extract sender for message ID generation
        try:
            msg = GemmailMessage.from_bytes(data)
            sender = msg.senders[0].address if msg.senders else ""
        except (ValueError, IndexError):
            sender = ""
        msg_id = generate_message_id(sender, timestamp)
        stem = f"{timestamp_str}-{msg_id}"

        if self.encryption_manager and self.encryption_manager.has_key(mailbox):
            filename = f"{stem}.gemmail.enc.new"
            filepath = mailbox_path / filename
            encrypted = self.encryption_manager.encrypt(mailbox, data)
            filepath.write_bytes(encrypted)
            is_encrypted = True
        else:
            filename = f"{stem}.gemmail.new"
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

    def _should_auto_reply(self, mailbox_path: Path, message: GemmailMessage) -> bool:
        """Check if an auto-reply should be sent for this message.

        Updates the rate-limit timestamp eagerly to prevent races when
        multiple messages from the same sender arrive simultaneously.
        """
        auto_reply_file = mailbox_path / ".auto-reply"
        if not auto_reply_file.exists():
            return False

        # Loop prevention: don't reply to auto-replies
        subject = message.subject or ""
        if "[Auto-Reply]" in subject:
            return False

        if not message.senders:
            return False

        # Rate limiting: don't reply to same sender within interval
        sender_addr = message.senders[0].address.lower()
        now = datetime.now(UTC)
        last_sent = self._auto_reply_last_sent.get(sender_addr)
        if last_sent is not None:
            elapsed = (now - last_sent).total_seconds()
            if elapsed < self.auto_reply_interval:
                logger.debug(
                    "auto_reply_rate_limited",
                    sender=sender_addr,
                    elapsed_seconds=int(elapsed),
                )
                return False

        # Eagerly record the timestamp to prevent duplicate sends
        # if another message arrives before the reply completes.
        self._auto_reply_last_sent[sender_addr] = now
        return True

    async def _send_auto_reply(
        self,
        mailbox: str,
        mailbox_path: Path,
        original: GemmailMessage,
    ) -> None:
        """Send an auto-reply to the first sender of the original message."""
        if not self.identity_certfile or not self.identity_keyfile:
            logger.warning("auto_reply_no_identity_cert")
            return

        auto_reply_file = mailbox_path / ".auto-reply"
        try:
            reply_body = auto_reply_file.read_text()
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("auto_reply_read_failed", error=str(e))
            return

        if not original.senders:
            return

        sender_addr = original.senders[0].address

        from ..client.session import MisfinClient

        try:
            async with MisfinClient(
                timeout=10.0,
                port=self.port,
                client_cert=self.identity_certfile,
                client_key=self.identity_keyfile,
            ) as client:
                response = await client.send(
                    to=sender_addr,
                    body=reply_body,
                    subject="[Auto-Reply]",
                )

            if 20 <= response.status < 30:
                logger.info(
                    "auto_reply_sent",
                    mailbox=mailbox,
                    recipient=sender_addr,
                )
            else:
                logger.warning(
                    "auto_reply_failed",
                    mailbox=mailbox,
                    recipient=sender_addr,
                    status=response.status,
                )
        except Exception as e:
            logger.warning(
                "auto_reply_error",
                mailbox=mailbox,
                recipient=sender_addr,
                error=str(e),
            )

    # -- Mailing list support --

    def _is_active_list(self, mailbox_path: Path) -> bool:
        """Return True if the mailbox is a mailing list and lists are enabled."""
        if not self.lists_enabled:
            return False
        return is_mailing_list(mailbox_path)

    def _check_list_posting(
        self,
        mailbox: str,
        mailbox_path: Path,
        senders: list[MisfinAddress],
        message_bytes: bytes,
    ) -> MisfinResponse | None:
        """Reject non-subscribers and loops for mailing lists.

        Returns an error response when posting is not allowed, or None
        to allow delivery to proceed.
        """
        if not self._is_active_list(mailbox_path):
            return None

        # Loop prevention: reject if the list address is already a recipient
        try:
            parsed = GemmailMessage.from_bytes(message_bytes)
            list_address = f"{mailbox}@{self.hostname}"
            if should_prevent_loop(parsed, list_address):
                logger.info("list_loop_prevented", mailbox=mailbox)
                return MisfinResponse(
                    status=StatusCode.BAD_REQUEST,
                    meta="Loop detected: list address in recipients",
                )
        except ValueError:
            pass

        subscribers = load_subscribers(mailbox_path)
        for sender in senders:
            if is_subscriber(sender.address, subscribers):
                return None

        logger.info(
            "list_post_rejected",
            mailbox=mailbox,
            senders=[s.address for s in senders],
        )
        return MisfinResponse(
            status=StatusCode.UNAUTHORIZED_SENDER,
            meta="Only subscribers may post to this list",
        )

    def _maybe_trigger_list_forwarding(
        self,
        mailbox: str,
        mailbox_path: Path,
        message_bytes: bytes,
    ) -> None:
        """Trigger mailing list forwarding if the mailbox is a list."""
        if not self._is_active_list(mailbox_path):
            return

        try:
            parsed_msg = GemmailMessage.from_bytes(message_bytes)
            subscribers = load_subscribers(mailbox_path)
            if not subscribers:
                return

            asyncio.ensure_future(
                self._forward_to_list(mailbox, mailbox_path, parsed_msg, subscribers)
            )
        except Exception:
            pass  # Never let list forwarding affect delivery

    async def _forward_to_list(
        self,
        mailbox: str,
        mailbox_path: Path,
        message: GemmailMessage,
        subscribers: list[str],
    ) -> None:
        """Forward a message to all list subscribers."""
        try:
            cert_path, key_path = get_or_create_list_identity(
                mailbox_path, mailbox, self.hostname
            )
        except Exception as e:
            logger.error(
                "list_identity_failed",
                mailbox=mailbox,
                error=str(e),
            )
            return

        sender_addr = message.senders[0].address.lower() if message.senders else ""

        from ..client.session import MisfinClient

        success_count = 0
        try:
            async with MisfinClient(
                timeout=10.0,
                port=self.port,
                client_cert=cert_path,
                client_key=key_path,
            ) as client:
                for subscriber in subscribers:
                    if subscriber == sender_addr:
                        continue
                    try:
                        response = await client.send(
                            to=subscriber,
                            body=message.body,
                            subject=message.subject,
                        )
                        if 20 <= response.status < 30:
                            success_count += 1
                        else:
                            logger.warning(
                                "list_forward_failed",
                                mailbox=mailbox,
                                recipient=subscriber,
                                status=response.status,
                            )
                    except Exception as e:
                        logger.warning(
                            "list_forward_error",
                            mailbox=mailbox,
                            recipient=subscriber,
                            error=str(e),
                        )
        except Exception as e:
            logger.error(
                "list_client_failed",
                mailbox=mailbox,
                error=str(e),
            )
            return

        logger.info(
            "list_forwarded",
            mailbox=mailbox,
            total=len(subscribers),
            sent=success_count,
        )
