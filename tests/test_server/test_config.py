"""Tests for ServerConfig."""

import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from titlani.protocol.constants import DEFAULT_PORT
from titlani.server.config import ServerConfig, ServerSection


class TestServerConfig:
    def test_defaults(self):
        config = ServerConfig()
        assert config.server.host == "localhost"
        assert config.server.port == DEFAULT_PORT
        assert config.server.hostname == "localhost"
        assert config.server.certfile is None
        assert config.server.keyfile is None

    def test_validate_invalid_port(self):
        with pytest.raises(ValidationError):
            ServerConfig(server=ServerSection(port=0))

    def test_validate_missing_certfile(self, tmp_path):
        config = ServerConfig(
            server=ServerSection(certfile=tmp_path / "nonexistent.pem")
        )
        with pytest.raises(ValueError, match="Certificate file not found"):
            config.validate_files()

    def test_from_toml(self, tmp_path):
        toml_content = """
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
mailbox_dir = "my_mailboxes"

[rate_limit]
enable = true
capacity = 5.0
refill_rate = 0.5
retry_after = 60
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)

        config = ServerConfig.from_toml(toml_file)
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 1958
        assert config.server.hostname == "mail.example.com"
        assert config.server.mailbox_dir == Path("my_mailboxes")
        assert config.rate_limit.enable is True
        assert config.rate_limit.capacity == 5.0
        assert config.rate_limit.refill_rate == 0.5
        assert config.rate_limit.retry_after == 60

    def test_from_toml_defaults(self, tmp_path):
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        config = ServerConfig.from_toml(toml_file)
        assert config.server.host == "localhost"
        assert config.server.port == DEFAULT_PORT

    def test_auto_reply_config(self, tmp_path):
        toml_content = """
[auto_reply]
enable = true
interval = 3600
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content)
        config = ServerConfig.from_toml(toml_file)
        assert config.auto_reply.enable is True
        assert config.auto_reply.interval == 3600

    def test_auto_reply_defaults(self, tmp_path):
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        config = ServerConfig.from_toml(toml_file)
        assert config.auto_reply.enable is False
        assert config.auto_reply.interval == 86400


class TestMailboxDirPermissions:
    def test_mailbox_dir_created_with_700(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(mailbox_dir, 0o700)
        mode = stat.S_IMODE(mailbox_dir.stat().st_mode)
        assert mode == 0o700
