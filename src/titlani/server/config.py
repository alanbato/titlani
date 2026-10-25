"""Misfin server configuration."""

import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_data_path
from pydantic import BaseModel, Field, field_validator, model_validator
from tlacacoca import ProxyProtocolConfig

from ..protocol.constants import DEFAULT_GMAP_PORT, DEFAULT_PORT

VerificationModeStr = Literal["off", "optional", "required"]
VerificationMethodStr = Literal["probe", "spki", "probe+spki"]
SPKIOnChangeStr = Literal["reject", "accept"]


def default_mailbox_dir() -> Path:
    return user_data_path("titlani") / "mail"


class ServerSection(BaseModel):
    host: str = "localhost"
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    hostname: str = "localhost"
    certfile: Path | None = None
    keyfile: Path | None = None
    mailbox_dir: Path = Field(default_factory=default_mailbox_dir)
    identity_certfile: Path | None = None
    identity_keyfile: Path | None = None
    identity_cert_dir: Path | None = None


class RateLimitSection(BaseModel):
    enable: bool = False
    capacity: int = 10
    refill_rate: float = 1.0
    retry_after: int = 30


class AccessControlSection(BaseModel):
    enable: bool = False
    allow_list: list[str] = Field(default_factory=list)
    deny_list: list[str] = Field(default_factory=list)
    default_allow: bool = True


class ProxyProtocolSection(BaseModel):
    """PROXY protocol support for running behind a TCP relay.

    Applies to both the Misfin and GMAP listeners. Connections from
    ``trusted_sources`` must start with a PROXY v1/v2 header; the client
    address it carries is used for rate limiting, access control and logs.
    """

    enable: bool = False
    trusted_sources: list[str] = Field(default_factory=list)
    header_timeout: float = Field(default=5.0, gt=0)

    @field_validator("trusted_sources")
    @classmethod
    def _validate_trusted_sources(cls, value: list[str]) -> list[str]:
        # Raises ValueError for anything that is not an IP or CIDR.
        ProxyProtocolConfig(trusted_sources=value)
        return value

    @model_validator(mode="after")
    def _require_sources_when_enabled(self) -> "ProxyProtocolSection":
        if self.enable and not self.trusted_sources:
            raise ValueError(
                "proxy_protocol.enable = true requires at least one entry in "
                "proxy_protocol.trusted_sources"
            )
        return self

    def to_tlacacoca(self) -> ProxyProtocolConfig | None:
        """Build the tlacacoca config, or None when disabled."""
        if not self.enable:
            return None
        return ProxyProtocolConfig(
            trusted_sources=list(self.trusted_sources),
            header_timeout=self.header_timeout,
        )


class VerificationSection(BaseModel):
    mode: VerificationModeStr = "off"
    method: VerificationMethodStr = "probe"
    cache_path: Path | None = None
    cache_ttl: int = 604800  # 7 days
    probe_timeout: float = 10.0
    spki_on_change: SPKIOnChangeStr = "reject"


class EncryptionSection(BaseModel):
    enable: bool = False
    key_dir: Path | None = None


class GmapSection(BaseModel):
    enable: bool = False
    port: int = Field(default=DEFAULT_GMAP_PORT, ge=1, le=65535)


class AutoReplySection(BaseModel):
    enable: bool = False
    interval: int = 86400  # seconds between replies to same sender


class ListsSection(BaseModel):
    enable: bool = False
    archive: bool = True  # store a copy of forwarded messages


class ServerConfig(BaseModel):
    server: ServerSection = Field(default_factory=ServerSection)
    rate_limit: RateLimitSection = Field(default_factory=RateLimitSection)
    access_control: AccessControlSection = Field(default_factory=AccessControlSection)
    proxy_protocol: ProxyProtocolSection = Field(default_factory=ProxyProtocolSection)
    verification: VerificationSection = Field(default_factory=VerificationSection)
    encryption: EncryptionSection = Field(default_factory=EncryptionSection)
    gmap: GmapSection = Field(default_factory=GmapSection)
    auto_reply: AutoReplySection = Field(default_factory=AutoReplySection)
    lists: ListsSection = Field(default_factory=ListsSection)

    @classmethod
    def from_toml(cls, path: Path) -> "ServerConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data)

    def validate_files(self) -> None:
        """Check configured certificate paths before startup.

        Missing files are fine: the server auto-generates certificates at the
        configured paths on first start.  A path that exists but is not a
        regular file (e.g. a directory) can never be used, so it is rejected.
        """
        paths = {
            "Certificate file": self.server.certfile,
            "Key file": self.server.keyfile,
            "Identity certificate file": self.server.identity_certfile,
            "Identity key file": self.server.identity_keyfile,
        }
        for label, path in paths.items():
            if path is not None and path.exists() and not path.is_file():
                raise ValueError(f"{label} is not a regular file: {path}")
