"""Misfin server configuration."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..protocol.constants import DEFAULT_PORT


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = DEFAULT_PORT
    hostname: str = "localhost"
    certfile: Path | None = None
    keyfile: Path | None = None
    mailbox_dir: Path = field(default_factory=lambda: Path("mailboxes"))
    identity_certfile: Path | None = None
    identity_keyfile: Path | None = None

    # Rate limiting
    rate_limit_enable: bool = False
    rate_limit_capacity: int = 10
    rate_limit_refill_rate: float = 1.0
    rate_limit_retry_after: int = 30

    # Access control
    access_control_enable: bool = False
    access_control_allow_list: list[str] = field(default_factory=list)
    access_control_deny_list: list[str] = field(default_factory=list)
    access_control_default_allow: bool = True

    @classmethod
    def from_toml(cls, path: Path) -> "ServerConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)

        server = data.get("server", {})
        rate_limit = data.get("rate_limit", {})
        access_control = data.get("access_control", {})

        config = cls(
            host=server.get("host", "localhost"),
            port=server.get("port", DEFAULT_PORT),
            hostname=server.get("hostname", "localhost"),
            mailbox_dir=Path(server.get("mailbox_dir", "mailboxes")),
        )

        if "certfile" in server:
            config.certfile = Path(server["certfile"])
        if "keyfile" in server:
            config.keyfile = Path(server["keyfile"])
        if "identity_certfile" in server:
            config.identity_certfile = Path(server["identity_certfile"])
        if "identity_keyfile" in server:
            config.identity_keyfile = Path(server["identity_keyfile"])

        config.rate_limit_enable = rate_limit.get("enable", False)
        config.rate_limit_capacity = int(rate_limit.get("capacity", 10))
        config.rate_limit_refill_rate = rate_limit.get("refill_rate", 1.0)
        config.rate_limit_retry_after = rate_limit.get("retry_after", 30)

        config.access_control_enable = access_control.get("enable", False)
        config.access_control_allow_list = access_control.get("allow_list", [])
        config.access_control_deny_list = access_control.get("deny_list", [])
        config.access_control_default_allow = access_control.get("default_allow", True)

        return config

    def validate(self) -> None:
        if self.certfile and not self.certfile.exists():
            raise ValueError(f"Certificate file not found: {self.certfile}")
        if self.keyfile and not self.keyfile.exists():
            raise ValueError(f"Key file not found: {self.keyfile}")
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")
