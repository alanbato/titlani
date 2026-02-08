"""Misfin(C) gemmail message format: metadata + body parsing."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..protocol.constants import MAX_METADATA_LINE_SIZE


@dataclass
class MisfinAddress:
    mailbox: str
    hostname: str
    blurb: str = ""

    @classmethod
    def parse(cls, text: str) -> "MisfinAddress":
        text = text.strip()
        if not text:
            raise ValueError("Empty address")
        parts = text.split(" ", 1)
        addr_part = parts[0]
        blurb = parts[1].strip() if len(parts) > 1 else ""
        if "," in blurb:
            raise ValueError(f"Blurb must not contain commas: {blurb!r}")
        if "@" in blurb:
            raise ValueError(f"Blurb must not contain '@' symbol: {blurb!r}")
        if "@" not in addr_part:
            raise ValueError(f"Invalid address format: {addr_part!r}")
        mailbox, hostname = addr_part.rsplit("@", 1)
        if not mailbox or not hostname:
            raise ValueError(f"Invalid address format: {addr_part!r}")
        return cls(mailbox=mailbox, hostname=hostname, blurb=blurb)

    @property
    def address(self) -> str:
        return f"{self.mailbox}@{self.hostname}"

    @property
    def long_form(self) -> str:
        if self.blurb:
            return f"{self.blurb} ({self.address})"
        return self.address

    def __str__(self) -> str:
        if self.blurb:
            return f"{self.address} {self.blurb}"
        return self.address


@dataclass
class GemmailMessage:
    senders: list[MisfinAddress] = field(default_factory=list)
    recipients: list[MisfinAddress] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    body: str = ""

    @classmethod
    def from_bytes(cls, data: bytes) -> "GemmailMessage":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"Message is not valid UTF-8: {e}") from e

        # Validate: CR only before LF
        for i, ch in enumerate(text):
            if ch == "\r" and (i + 1 >= len(text) or text[i + 1] != "\n"):
                raise ValueError("CR must only appear immediately before LF")

        # Normalize line endings to LF for parsing
        text = text.replace("\r\n", "\n")
        lines = text.split("\n")

        # Need at least 3 metadata lines (may have trailing empty from
        # final newline)
        # Filter: if last element is empty string from trailing \n, keep it
        # but we need at least 3 actual line terminators
        if len(lines) < 4:  # 3 metadata lines + at least empty trailing
            raise ValueError("Message must have at least 3 metadata lines")

        # Parse metadata lines and validate sizes
        for i in range(3):
            line_bytes = (lines[i] + "\n").encode("utf-8")
            if len(line_bytes) > MAX_METADATA_LINE_SIZE:
                raise ValueError(
                    f"Metadata line {i + 1} exceeds {MAX_METADATA_LINE_SIZE} bytes"
                )

        senders = _parse_address_line(lines[0])
        recipients = _parse_address_line(lines[1])
        timestamps = _parse_timestamp_line(lines[2])

        # Body is everything after the 3 metadata lines
        body = "\n".join(lines[3:])

        return cls(
            senders=senders,
            recipients=recipients,
            timestamps=timestamps,
            body=body,
        )

    def to_bytes(self) -> bytes:
        sender_line = ", ".join(str(s) for s in self.senders)
        recipient_line = ", ".join(str(r) for r in self.recipients)
        timestamp_line = ", ".join(
            ts.strftime("%Y-%m-%dT%H:%M:%SZ") for ts in self.timestamps
        )
        parts = [sender_line, recipient_line, timestamp_line]
        metadata = "\n".join(parts) + "\n"
        return (metadata + self.body).encode("utf-8")

    @property
    def subject(self) -> str | None:
        for line in self.body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") and not stripped.startswith("##"):
                return stripped.lstrip("#").strip()
            if stripped.startswith("##"):
                return stripped.lstrip("#").strip()
        return None


def _parse_address_line(line: str) -> list[MisfinAddress]:
    line = line.strip()
    if not line:
        return []
    items = line.split(",")
    addresses = []
    for item in items:
        item = item.strip()
        if item:
            addresses.append(MisfinAddress.parse(item))
    return addresses


def _parse_timestamp_line(line: str) -> list[datetime]:
    line = line.strip()
    if not line:
        return []
    items = line.split(",")
    timestamps = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        try:
            ts = datetime.fromisoformat(item.replace("Z", "+00:00"))
            timestamps.append(ts.astimezone(UTC))
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {item!r}") from e
    return timestamps
