"""Misfin response representation."""

from dataclasses import dataclass

from .status import is_redirect, is_success


@dataclass(frozen=True)
class MisfinResponse:
    status: int
    meta: str

    @classmethod
    def from_line(cls, line: str) -> "MisfinResponse":
        parts = line.split(" ", 1)
        if not parts:
            raise ValueError("Empty response line")
        try:
            status = int(parts[0])
        except ValueError as e:
            raise ValueError(f"Invalid status code: {parts[0]}") from e
        meta = parts[1] if len(parts) > 1 else ""
        return cls(status=status, meta=meta)

    def to_bytes(self) -> bytes:
        return f"{self.status} {self.meta}\r\n".encode()

    @property
    def fingerprint(self) -> str | None:
        if is_success(self.status):
            return self.meta.strip() or None
        return None

    @property
    def redirect_address(self) -> str | None:
        if is_redirect(self.status):
            return self.meta.strip() or None
        return None
