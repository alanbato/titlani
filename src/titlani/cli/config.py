"""Client-side configuration for Titlani CLI."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path


@dataclass
class ClientConfig:
    mailbox_dir: Path

    @classmethod
    def from_toml(cls, path: Path) -> "ClientConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)

        mail = data.get("mail", {})
        mailbox_dir = mail.get("mailbox_dir")

        # Fall back to server config's mailbox_dir
        if mailbox_dir is None:
            server_config = mail.get("server_config")
            if server_config:
                mailbox_dir = cls._read_server_mailbox_dir(
                    Path(server_config)
                )

        if mailbox_dir is None:
            raise ValueError(
                "Missing required key: [mail] mailbox_dir "
                "(or server_config pointing to server TOML)"
            )
        return cls(mailbox_dir=Path(mailbox_dir))

    @staticmethod
    def _read_server_mailbox_dir(path: Path) -> str | None:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return data.get("server", {}).get("mailbox_dir")

    @classmethod
    def load(cls) -> "ClientConfig | None":
        """Load from XDG config path; return None if absent."""
        config_dir = user_config_path("titlani")
        config_file = config_dir / "config.toml"
        if not config_file.exists():
            return None
        return cls.from_toml(config_file)
