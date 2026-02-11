"""Tests for identity certificate commands."""

from pathlib import Path

from typer.testing import CliRunner

from titlani.__main__ import app

runner = CliRunner()


class TestIdentityGenerateInstall:
    """Test --install flag on identity generate."""

    def _write_server_toml(self, config_dir: Path, mailbox_dir: Path) -> Path:
        config_path = config_dir / "server.toml"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            f'[server]\nhostname = "example.com"\nmailbox_dir = "{mailbox_dir}"\n'
        )
        return config_path

    def test_install_copies_pem_to_cert_dir(self, tmp_path):
        output_dir = tmp_path / "output"
        mailbox_dir = tmp_path / "mail"
        config_path = self._write_server_toml(tmp_path / "config", mailbox_dir)

        result = runner.invoke(
            app,
            [
                "identity",
                "generate",
                "alice",
                "example.com",
                "--output-dir",
                str(output_dir),
                "--install",
                "--config",
                str(config_path),
            ],
        )
        assert result.exit_code == 0, result.output

        # The .pem should be copied to mailbox_dir (fallback cert dir)
        assert (mailbox_dir / "alice.pem").exists()
        # Original cert should still exist
        assert (output_dir / "alice.pem").exists()

    def test_install_creates_mailbox_subdirectory(self, tmp_path):
        output_dir = tmp_path / "output"
        mailbox_dir = tmp_path / "mail"
        config_path = self._write_server_toml(tmp_path / "config", mailbox_dir)

        result = runner.invoke(
            app,
            [
                "identity",
                "generate",
                "bob",
                "example.com",
                "--output-dir",
                str(output_dir),
                "--install",
                "--config",
                str(config_path),
            ],
        )
        assert result.exit_code == 0, result.output

        # Mailbox subdirectory should be created
        assert (mailbox_dir / "bob").is_dir()

    def test_install_uses_identity_cert_dir(self, tmp_path):
        output_dir = tmp_path / "output"
        mailbox_dir = tmp_path / "mail"
        cert_dir = tmp_path / "certs"
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "server.toml"
        config_path.write_text(
            f'[server]\nhostname = "example.com"\n'
            f'mailbox_dir = "{mailbox_dir}"\n'
            f'identity_cert_dir = "{cert_dir}"\n'
        )

        result = runner.invoke(
            app,
            [
                "identity",
                "generate",
                "alice",
                "example.com",
                "--output-dir",
                str(output_dir),
                "--install",
                "--config",
                str(config_path),
            ],
        )
        assert result.exit_code == 0, result.output

        # Should go to identity_cert_dir, not mailbox_dir
        assert (cert_dir / "alice.pem").exists()
        assert not (mailbox_dir / "alice.pem").exists()

    def test_install_without_config_fails(self, tmp_path):
        output_dir = tmp_path / "output"
        nonexistent = tmp_path / "does_not_exist.toml"

        result = runner.invoke(
            app,
            [
                "identity",
                "generate",
                "alice",
                "example.com",
                "--output-dir",
                str(output_dir),
                "--install",
                "--config",
                str(nonexistent),
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
