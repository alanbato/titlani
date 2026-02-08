"""Misfin(C) request representation.

Request format: misfin://<MAILBOX>@<HOSTNAME><TAB><CONTENT-LENGTH><CR><LF><MESSAGE>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cryptography import x509

from .constants import (
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

    def to_bytes(self) -> bytes:
        header = (
            f"{MISFIN_SCHEME}://{self.mailbox}@{self.hostname}\t{self.content_length}\r\n"
        )
        return header.encode("utf-8") + self.raw_message

    def parse_message(self) -> GemmailMessage:
        from ..content.gemmail import GemmailMessage

        return GemmailMessage.from_bytes(self.raw_message)
