"""Misfin(C) request representation.

Request format: misfin://<MAILBOX>@<HOSTNAME><TAB><CONTENT-LENGTH><CR><LF><MESSAGE>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cryptography import x509

from .constants import (
    MAX_B_REQUEST_SIZE,
    MAX_CONTENT_LENGTH,
    MAX_HEADER_SIZE,
    MISFIN_SCHEME,
)

if TYPE_CHECKING:
    from ..content.gemmail import GemmailMessage


@dataclass
class MisfinRequest:
    mailbox: str
    hostname: str
    content_length: int
    raw_message: bytes = b""
    raw_header: bytes = b""
    client_cert: x509.Certificate | None = field(default=None, repr=False)
    client_cert_fingerprint: str | None = None
    protocol_version: str = "C"
    verification_result: Any = field(default=None, repr=False)

    @classmethod
    def from_header(cls, header_line: bytes) -> MisfinRequest:
        if len(header_line) > MAX_HEADER_SIZE:
            raise ValueError(f"Header exceeds maximum size ({MAX_HEADER_SIZE} bytes)")
        try:
            header_str = header_line.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid UTF-8 in header: {e}") from e

        if "\t" not in header_str:
            raise ValueError("Missing TAB separator in header")

        uri_part, length_part = header_str.split("\t", 1)

        # Validate scheme
        prefix = f"{MISFIN_SCHEME}://"
        if not uri_part.startswith(prefix):
            raise ValueError(f"Invalid scheme: expected {MISFIN_SCHEME}://")

        address = uri_part[len(prefix) :]
        if "@" not in address:
            raise ValueError(f"Invalid address format: {address!r}")

        mailbox, hostname = address.rsplit("@", 1)
        if not mailbox or not hostname:
            raise ValueError(f"Invalid address format: {address!r}")

        try:
            content_length = int(length_part.strip())
        except ValueError as e:
            raise ValueError(f"Invalid content length: {length_part!r}") from e

        if content_length < 0:
            raise ValueError(f"Content length must be non-negative: {content_length}")
        if content_length > MAX_CONTENT_LENGTH:
            raise ValueError(
                f"Content length {content_length} exceeds maximum "
                f"({MAX_CONTENT_LENGTH} bytes)"
            )

        return cls(
            mailbox=mailbox,
            hostname=hostname,
            content_length=content_length,
            raw_header=header_line,
        )

    @classmethod
    def from_header_b(cls, header_line: bytes) -> MisfinRequest:
        if len(header_line) > MAX_B_REQUEST_SIZE:
            raise ValueError(
                f"B request exceeds maximum size ({MAX_B_REQUEST_SIZE} bytes)"
            )
        try:
            header_str = header_line.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid UTF-8 in header: {e}") from e

        prefix = f"{MISFIN_SCHEME}://"
        if not header_str.startswith(prefix):
            raise ValueError(f"Invalid scheme: expected {MISFIN_SCHEME}://")

        remainder = header_str[len(prefix) :]
        space_idx = remainder.find(" ")
        if space_idx == -1:
            raise ValueError("Missing space separator in B request")

        address = remainder[:space_idx]
        message_text = remainder[space_idx + 1 :]

        if "@" not in address:
            raise ValueError(f"Invalid address format: {address!r}")

        mailbox, hostname = address.rsplit("@", 1)
        if not mailbox or not hostname:
            raise ValueError(f"Invalid address format: {address!r}")

        if not message_text:
            raise ValueError("Empty message in B request")

        raw_message = message_text.encode("utf-8")
        return cls(
            mailbox=mailbox,
            hostname=hostname,
            content_length=len(raw_message),
            raw_message=raw_message,
            raw_header=header_line,
            protocol_version="B",
        )

    def to_bytes(self) -> bytes:
        header = (
            f"{MISFIN_SCHEME}://{self.mailbox}@{self.hostname}\t{self.content_length}\r\n"
        )
        return header.encode("utf-8") + self.raw_message

    def to_bytes_b(self) -> bytes:
        if self.raw_message:
            body_text = self.raw_message.decode("utf-8")
            # Strip gemmail metadata (first 3 lines) if present
            lines = body_text.split("\n")
            if len(lines) >= 4:
                body_text = "\n".join(lines[3:])
            # Collapse newlines to spaces for B format
            body_text = " ".join(body_text.split())
        else:
            body_text = ""

        result = f"{MISFIN_SCHEME}://{self.mailbox}@{self.hostname} {body_text}\r\n"
        result_bytes = result.encode("utf-8")
        if len(result_bytes) > MAX_B_REQUEST_SIZE + 2:  # +2 for CRLF
            raise ValueError(
                f"B request exceeds maximum size ({MAX_B_REQUEST_SIZE} bytes)"
            )
        return result_bytes

    def parse_message(self) -> GemmailMessage:
        from ..content.gemmail import GemmailMessage

        return GemmailMessage.from_bytes(self.raw_message)
