"""Tests for the init wizard command."""

from pathlib import Path

from typer.testing import CliRunner

from titlani.__main__ import app
from titlani.server.config import ServerConfig, default_mailbox_dir

runner = CliRunner()

# Default wizard input: accept all defaults, decline all features
DEFAULT_INPUT = "\n".join([
    "",        # hostname: localhost
    "",        # port: 1958
    "",        # mailbox_dir: default
    "n",       # GMAP
    "n",       # verification
    "n",       # encryption
    "n",       # auto-reply
    "n",       # rate limiting
    "n",       # access control
    "",
])

# Enable all features with details
ALL_FEATURES_INPUT = "\n".join([
    "mail.example.com",  # hostname
    "1959",              # port
    "/tmp/mail",         # mailbox_dir
    "y",                 # GMAP
    "y",                 # verification
    "y",                 # encryption
    "y",                 # auto-reply
    "y",                 # rate limiting
    "y",                 # access control
    "required",          # verification mode
    "3600",              # auto-reply interval
    "20",                # rate limit capacity
    "2.0",               # refill rate
    "y",                 # default allow
    "",
])


class TestInitWizard:
    def test_writes_both_config_files(self, tmp_path):
        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path)],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 0
        assert (tmp_path / "server.toml").exists()
        assert (tmp_path / "config.toml").exists()

    def test_generated_server_toml_is_valid(self, tmp_path):
        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path)],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 0

        config = ServerConfig.from_toml(tmp_path / "server.toml")
        assert config.hostname == "localhost"
        assert config.port == 1958
        assert config.mailbox_dir == default_mailbox_dir()

    def test_client_toml_references_server_config(self, tmp_path):
        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path)],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 0

        content = (tmp_path / "config.toml").read_text()
        assert "server_config" in content
        assert str(tmp_path / "server.toml") in content

    def test_custom_values(self, tmp_path):
        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path)],
            input=ALL_FEATURES_INPUT,
        )
        assert result.exit_code == 0

        config = ServerConfig.from_toml(tmp_path / "server.toml")
        assert config.hostname == "mail.example.com"
        assert config.port == 1959
        assert config.mailbox_dir == Path("/tmp/mail")
        assert config.gmap_enable is True
        assert config.verification_mode == "required"
        assert config.encryption_enable is True
        assert config.auto_reply_enable is True
        assert config.auto_reply_interval == 3600
        assert config.rate_limit_enable is True
        assert config.rate_limit_capacity == 20
        assert config.rate_limit_refill_rate == 2.0
        assert config.access_control_enable is True
        assert config.access_control_default_allow is True

    def test_refuses_overwrite_without_force(self, tmp_path):
        (tmp_path / "server.toml").write_text("")

        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path)],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 1
        assert "already exist" in result.output

    def test_force_overwrites(self, tmp_path):
        (tmp_path / "server.toml").write_text("old")
        (tmp_path / "config.toml").write_text("old")

        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path), "--force"],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 0
        assert (tmp_path / "server.toml").read_text() != "old"
        assert (tmp_path / "config.toml").read_text() != "old"

    def test_creates_output_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        result = runner.invoke(
            app,
            ["init", "--output-dir", str(nested)],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 0
        assert nested.exists()
        assert (nested / "server.toml").exists()

    def test_features_disabled_by_default(self, tmp_path):
        result = runner.invoke(
            app,
            ["init", "--output-dir", str(tmp_path)],
            input=DEFAULT_INPUT,
        )
        assert result.exit_code == 0

        config = ServerConfig.from_toml(tmp_path / "server.toml")
        assert config.gmap_enable is False
        assert config.verification_mode == "off"
        assert config.encryption_enable is False
        assert config.auto_reply_enable is False
        assert config.rate_limit_enable is False
        assert config.access_control_enable is False


class TestServeAutoDiscover:
    def test_serve_no_config_suggests_init(self, tmp_path, mocker):
        mocker.patch(
            "titlani.cli.commands.serve.DEFAULT_SERVER_CONFIG",
            tmp_path / "nonexistent" / "server.toml",
        )
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 1
        assert "titlani init" in result.output
