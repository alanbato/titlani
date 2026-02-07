"""Tests for ServerConfig."""

from pathlib import Path

import pytest

from titlani.protocol.constants import DEFAULT_PORT
from titlani.server.config import ServerConfig


class TestServerConfig:
    def test_defaults(self):
        config = ServerConfig()
        assert config.host == "localhost"
        assert config.port == DEFAULT_PORT
        assert config.hostname == "localhost"
        assert config.certfile is None
        assert config.keyfile is None

    def test_validate_invalid_port(self):
        config = ServerConfig(port=0)
        with pytest.raises(ValueError, match="Invalid port"):
            config.validate()

    def test_validate_missing_certfile(self, tmp_path):
        config = ServerConfig(certfile=tmp_path / "nonexistent.pem")
        with pytest.raises(ValueError, match="Certificate file not found"):
            config.validate()

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
        assert config.host == "0.0.0.0"
        assert config.port == 1958
        assert config.hostname == "mail.example.com"
        assert config.mailbox_dir == Path("my_mailboxes")
        assert config.rate_limit_enable is True
        assert config.rate_limit_capacity == 5.0
        assert config.rate_limit_refill_rate == 0.5
        assert config.rate_limit_retry_after == 60

    def test_from_toml_defaults(self, tmp_path):
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        config = ServerConfig.from_toml(toml_file)
        assert config.host == "localhost"
        assert config.port == DEFAULT_PORT
