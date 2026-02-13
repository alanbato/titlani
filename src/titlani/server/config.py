"""Misfin server configuration."""

import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_data_path
from pydantic import BaseModel, Field

from ..protocol.constants import DEFAULT_GMAP_PORT, DEFAULT_PORT

VerificationModeStr = Literal["off", "optional", "required"]
VerificationMethodStr = Literal["probe", "spki"]
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
    access_control: AccessControlSection = Field(
        default_factory=AccessControlSection
    )
    verification: VerificationSection = Field(
        default_factory=VerificationSection
    )
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
        if self.server.certfile and not self.server.certfile.exists():
            raise ValueError(
                f"Certificate file not found: {self.server.certfile}"
            )
        if self.server.keyfile and not self.server.keyfile.exists():
            raise ValueError(
                f"Key file not found: {self.server.keyfile}"
            )
