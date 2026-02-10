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
        if mailbox_dir is None:
            raise ValueError("Missing required key: [mail] mailbox_dir")
        return cls(mailbox_dir=Path(mailbox_dir))

    @classmethod
    def load(cls) -> "ClientConfig | None":
        """Load from XDG config path; return None if absent."""
        config_dir = user_config_path("titlani")
        config_file = config_dir / "config.toml"
        if not config_file.exists():
            return None
        return cls.from_toml(config_file)
