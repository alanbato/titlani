"""GMAP request routing and message retrieval.

Routes GMAP Gemini requests to mailbox operations, handling
authentication via client certificates.
"""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from tlacacoca import get_certificate_fingerprint, get_logger

from ..identity.certificate import extract_identity, normalize_fingerprint
from ..server.lists import (
    get_list_description,
    is_mailing_list,
    load_subscribers,
)
from .mailbox import GmapMailbox, _valid_tag

logger = get_logger(__name__)

# Gemini status codes used by GMAP
SUCCESS = 20
REDIRECT_TEMP = 30
BAD_REQUEST = 59
CERT_REQUIRED = 60
CERT_NOT_AUTHORIZED = 61
NOT_FOUND = 51
TEMP_FAILURE = 40

MAX_GEMINI_REQUEST_SIZE = 1024


@dataclass(frozen=True)
class GeminiRequest:
    url: str
    hostname: str
    path: str
    query: str | None
    client_cert: x509.Certificate | None


@dataclass(frozen=True)
class GeminiResponse:
    status: int
    meta: str
    body: bytes = b""

    def to_bytes(self) -> bytes:
        header = f"{self.status} {self.meta}\r\n".encode()
        return header + self.body


# Route patterns
_MSGID_RE = re.compile(r"^/msgid/(.+)$")
_TAG_LIST_RE = re.compile(r"^/tag/$")
_TAG_NAME_RE = re.compile(r"^/tag/([^/?]+)$")
_TAG_NAME_SINCE_RE = re.compile(r"^/tag/([^/?]+)/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$")
_UNTAG_RE = re.compile(r"^/untag/([^/?]+)$")
_DELETE_RE = re.compile(r"^/delete$")
_LIST_RE = re.compile(r"^/list/$")
_LIST_INFO_RE = re.compile(r"^/list/([^/?]+)/info$")


class GmapHandler:
    """Routes GMAP requests and manages per-mailbox indices."""

    def __init__(
        self,
        mailbox_dir: Path,
        hostname: str,
        recipient_fps: dict[str, str] | None = None,
    ) -> None:
        self.mailbox_dir = mailbox_dir
        self.hostname = hostname
        self.recipient_fps = recipient_fps or {}

    def _verify_fingerprint(
        self,
        mailbox: str,
        client_cert: x509.Certificate,
    ) -> GeminiResponse | None:
        """Verify client cert fingerprint. Returns error response or None."""
        if not self.recipient_fps:
            return None
        expected_fp = self.recipient_fps.get(mailbox)
        if expected_fp is None:
            logger.warning(
                "gmap_auth_no_registration",
                mailbox=mailbox,
            )
            return GeminiResponse(
                CERT_NOT_AUTHORIZED,
                "No registered identity for mailbox",
            )
        client_fp = normalize_fingerprint(get_certificate_fingerprint(client_cert))
        if client_fp != expected_fp:
            logger.warning(
                "gmap_auth_fingerprint_mismatch",
                mailbox=mailbox,
                expected=expected_fp[:16] + "...",
                got=client_fp[:16] + "...",
            )
            return GeminiResponse(
                CERT_NOT_AUTHORIZED,
                "Certificate fingerprint mismatch",
            )
        return None

    async def handle_request(self, request: GeminiRequest) -> GeminiResponse:
        logger.debug(
            "gmap_handle_request",
            path=request.path,
            has_cert=request.client_cert is not None,
        )

        # Public /list/ routes — no cert required
        if request.path.startswith("/list/"):
            return self._route_list(request.path)

        # Authenticate and resolve mailbox
        result = self._authenticate(request)
        if isinstance(result, GeminiResponse):
            return result

        mbox = result
        if mbox.sync_filesystem():
            mbox.save()

        return self._route(request.path, request.query, mbox, request)

    def _authenticate(self, request: GeminiRequest) -> GmapMailbox | GeminiResponse:
        """Verify client cert and resolve mailbox. Returns the mailbox
        on success or an error response on failure."""
        if request.client_cert is None:
            logger.debug("gmap_auth_no_cert")
            return GeminiResponse(CERT_REQUIRED, "Client certificate required")

        try:
            identity = extract_identity(request.client_cert)
        except Exception:
            logger.warning("gmap_auth_invalid_cert")
            return GeminiResponse(CERT_NOT_AUTHORIZED, "Invalid certificate")

        if not identity.mailbox or not identity.hostname:
            logger.warning("gmap_auth_incomplete_identity")
            return GeminiResponse(CERT_NOT_AUTHORIZED, "Certificate missing identity")

        mailbox = identity.mailbox
        if (
            not mailbox
            or "\x00" in mailbox
            or "/" in mailbox
            or "\\" in mailbox
            or ".." in mailbox
            or not re.fullmatch(r"[a-zA-Z0-9._-]+", mailbox)
        ):
            logger.warning("gmap_auth_invalid_mailbox", mailbox=repr(mailbox))
            return GeminiResponse(CERT_NOT_AUTHORIZED, "Invalid mailbox name")

        fp_error = self._verify_fingerprint(mailbox, request.client_cert)
        if fp_error is not None:
            return fp_error

        mailbox_path = self.mailbox_dir / mailbox
        try:
            resolved = mailbox_path.resolve(strict=False)
            dir_resolved = self.mailbox_dir.resolve(strict=False)
            if not str(resolved).startswith(str(dir_resolved) + os.sep):
                return GeminiResponse(CERT_NOT_AUTHORIZED, "Invalid mailbox")
        except (OSError, ValueError):
            return GeminiResponse(CERT_NOT_AUTHORIZED, "Invalid mailbox")

        if not mailbox_path.is_dir():
            logger.info("gmap_auth_mailbox_not_found", mailbox=mailbox)
            return GeminiResponse(NOT_FOUND, "Mailbox not found")

        mbox = GmapMailbox(mailbox_path)
        mbox.load()
        logger.debug("gmap_auth_success", mailbox=mailbox)
        return mbox

    def _route(
        self,
        path: str,
        query: str | None,
        mbox: GmapMailbox,
        request: GeminiRequest,
    ) -> GeminiResponse:
        # /msgid/<id>
        m = _MSGID_RE.match(path)
        if m:
            return self._handle_msgid(m.group(1), mbox)

        # /tag/... routes
        if path.startswith("/tag/") or path == "/tag/":
            return self._route_tag(path, query, mbox)

        # /untag/<name>?<msgid>
        m = _UNTAG_RE.match(path)
        if m:
            if query is None:
                return GeminiResponse(BAD_REQUEST, "Message ID required")
            return self._handle_remove_tag(m.group(1), query, mbox)

        # /delete?<msgid>
        if _DELETE_RE.match(path):
            if query is None:
                return GeminiResponse(BAD_REQUEST, "Message ID required")
            return self._handle_delete(query, mbox)

        return GeminiResponse(NOT_FOUND, "Unknown route")

    def _route_tag(
        self,
        path: str,
        query: str | None,
        mbox: GmapMailbox,
    ) -> GeminiResponse:
        # /tag/ (all messages)
        if _TAG_LIST_RE.match(path):
            if query is not None:
                return GeminiResponse(BAD_REQUEST, "No query expected")
            return self._handle_tag_list_all(mbox)

        # /tag/<name>/timestamp (since filter)
        m = _TAG_NAME_SINCE_RE.match(path)
        if m:
            return self._handle_tag_list(
                m.group(1), mbox, since_str=m.group(2), query=query
            )

        # /tag/<name> (with optional ?msgid for tagging)
        m = _TAG_NAME_RE.match(path)
        if m:
            tag_name = m.group(1)
            if query is not None:
                return self._handle_add_tag(tag_name, query, mbox)
            return self._handle_tag_list(tag_name, mbox)

        return GeminiResponse(NOT_FOUND, "Unknown tag route")

    def _handle_msgid(self, msgid: str, mbox: GmapMailbox) -> GeminiResponse:
        if not mbox.has_message(msgid):
            return GeminiResponse(NOT_FOUND, "Message not found")

        if mbox.is_encrypted(msgid):
            return GeminiResponse(TEMP_FAILURE, "Message is encrypted")

        data = mbox.get_message_bytes(msgid)
        if data is None:
            return GeminiResponse(NOT_FOUND, "Message file missing")

        return GeminiResponse(SUCCESS, "text/plain", data)

    def _handle_tag_list_all(self, mbox: GmapMailbox) -> GeminiResponse:
        msgids = mbox.list_all_msgids()
        body = ", ".join(msgids)
        return GeminiResponse(SUCCESS, "text/plain", body.encode("utf-8"))

    def _handle_tag_list(
        self,
        tag: str,
        mbox: GmapMailbox,
        since_str: str | None = None,
        query: str | None = None,
    ) -> GeminiResponse:
        since = None
        if since_str:
            try:
                since = datetime.fromisoformat(
                    since_str.replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                return GeminiResponse(BAD_REQUEST, "Invalid timestamp")

        msgids = mbox.list_by_tag(tag, since=since)
        body = ", ".join(msgids)
        return GeminiResponse(SUCCESS, "text/plain", body.encode("utf-8"))

    def _handle_add_tag(self, tag: str, msgid: str, mbox: GmapMailbox) -> GeminiResponse:
        if not _valid_tag(tag):
            return GeminiResponse(BAD_REQUEST, "Invalid tag name")
        if not mbox.has_message(msgid):
            return GeminiResponse(NOT_FOUND, "Message not found")

        mbox.add_tag(msgid, tag)
        mbox.save()
        logger.info(
            "gmap_tag_added",
            mailbox=str(mbox.mailbox_path.name),
            msgid=msgid,
            tag=tag,
        )
        return GeminiResponse(SUCCESS, "text/plain", b"Tag added")

    def _handle_remove_tag(
        self, tag: str, msgid: str, mbox: GmapMailbox
    ) -> GeminiResponse:
        if not mbox.has_message(msgid):
            return GeminiResponse(NOT_FOUND, "Message not found")

        mbox.remove_tag(msgid, tag)
        mbox.save()
        logger.info(
            "gmap_tag_removed",
            mailbox=str(mbox.mailbox_path.name),
            msgid=msgid,
            tag=tag,
        )
        return GeminiResponse(SUCCESS, "text/plain", b"Tag removed")

    def _route_list(self, path: str) -> GeminiResponse:
        if _LIST_RE.match(path):
            return self._handle_list_discovery()

        m = _LIST_INFO_RE.match(path)
        if m:
            return self._handle_list_info(m.group(1))

        return GeminiResponse(NOT_FOUND, "Unknown list route")

    def _handle_list_discovery(self) -> GeminiResponse:
        lines: list[str] = []
        for entry in sorted(self.mailbox_dir.iterdir()):
            if entry.is_dir() and is_mailing_list(entry):
                lines.append(f"=> /list/{entry.name} {entry.name}")
        body = "\n".join(lines) + "\n" if lines else ""
        return GeminiResponse(SUCCESS, "text/gemini", body.encode("utf-8"))

    def _handle_list_info(self, name: str) -> GeminiResponse:
        list_path = self.mailbox_dir / name
        if not list_path.is_dir() or not is_mailing_list(list_path):
            return GeminiResponse(NOT_FOUND, "List not found")

        description = get_list_description(list_path) or ""
        subscribers = load_subscribers(list_path)
        msg_count = sum(
            1
            for p in list_path.iterdir()
            if p.name.endswith(".gemmail")
            or p.name.endswith(".gemmail.new")
            or p.name.endswith(".gemmail.enc")
            or p.name.endswith(".gemmail.enc.new")
        )
        address = f"{name}@{self.hostname}"

        lines = [f"# {name}"]
        if description:
            lines.append(description)
        lines.append(f"Subscribers: {len(subscribers)}")
        lines.append(f"Messages: {msg_count}")
        lines.append("")
        lines.append(f"=> misfin:{address}?subscribe Subscribe to this list")
        lines.append(f"=> misfin:{address}?unsubscribe Unsubscribe from this list")
        body = "\n".join(lines) + "\n"
        return GeminiResponse(SUCCESS, "text/gemini", body.encode("utf-8"))

    def _handle_delete(self, msgid: str, mbox: GmapMailbox) -> GeminiResponse:
        if not mbox.has_message(msgid):
            return GeminiResponse(NOT_FOUND, "Message not found")

        if not mbox.delete_message(msgid):
            logger.debug(
                "gmap_delete_not_in_trash",
                mailbox=str(mbox.mailbox_path.name),
                msgid=msgid,
            )
            return GeminiResponse(NOT_FOUND, "Message not in Trash")

        mbox.save()
        logger.info(
            "gmap_message_deleted",
            mailbox=str(mbox.mailbox_path.name),
            msgid=msgid,
        )
        return GeminiResponse(SUCCESS, "text/plain", b"Message deleted")


def parse_gemini_request(
    line: bytes,
    client_cert: x509.Certificate | None = None,
) -> GeminiRequest:
    """Parse a Gemini request line into a GeminiRequest.

    Format: gemini://hostname/path?query
    """
    try:
        text = line.decode("utf-8").strip()
    except UnicodeDecodeError as e:
        raise ValueError(f"Invalid UTF-8 in request: {e}") from e

    if not text.startswith("gemini://"):
        raise ValueError(f"Not a Gemini URL: {text!r}")

    # Strip scheme
    rest = text[len("gemini://") :]

    # Split host from path
    slash_idx = rest.find("/")
    if slash_idx == -1:
        hostname = rest
        path = "/"
    else:
        hostname = rest[:slash_idx]
        path = rest[slash_idx:]

    # Strip port from hostname if present
    if ":" in hostname:
        hostname = hostname.split(":")[0]

    # Split path from query
    query = None
    if "?" in path:
        path, query = path.split("?", 1)

    return GeminiRequest(
        url=text,
        hostname=hostname,
        path=path,
        query=query,
        client_cert=client_cert,
    )
