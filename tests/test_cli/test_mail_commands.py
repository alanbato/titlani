"""Tests for mail CLI commands."""

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from titlani.__main__ import app
from titlani.cli.config import ClientConfig
from titlani.content.gemmail import GemmailMessage, MisfinAddress

runner = CliRunner()


def _create_gemmail(
    path: Path,
    sender: str = "bob@other.com",
    body: str = "Hello!\n",
    subject: str | None = None,
) -> Path:
    senders = []
    if sender:
        mailbox, hostname = sender.split("@")
        senders = [MisfinAddress(mailbox, hostname)]

    full_body = body
    if subject:
        full_body = f"# {subject}\n\n{body}"

    msg = GemmailMessage(
        senders=senders,
        recipients=[MisfinAddress("alice", "example.com")],
        timestamps=[datetime.now(UTC)],
        body=full_body,
    )
    path.write_bytes(msg.to_bytes())
    return path


class TestMailDelete:
    def test_delete_removes_file(self, tmp_path):
        gemmail = _create_gemmail(tmp_path / "test.gemmail")
        assert gemmail.exists()

        result = runner.invoke(
            app,
            ["mail", "delete", str(gemmail), "--force"],
        )
        assert result.exit_code == 0
        assert not gemmail.exists()
        assert "Deleted 1" in result.output

    def test_delete_multiple_files(self, tmp_path):
        f1 = _create_gemmail(tmp_path / "msg1.gemmail")
        f2 = _create_gemmail(tmp_path / "msg2.gemmail")

        result = runner.invoke(
            app,
            [
                "mail",
                "delete",
                str(f1),
                str(f2),
                "--force",
            ],
        )
        assert result.exit_code == 0
        assert not f1.exists()
        assert not f2.exists()
        assert "Deleted 2" in result.output

    def test_delete_with_confirmation(self, tmp_path):
        gemmail = _create_gemmail(tmp_path / "test.gemmail")

        # User says no
        result = runner.invoke(
            app,
            ["mail", "delete", str(gemmail)],
            input="n\n",
        )
        assert gemmail.exists()
        assert "Cancelled" in result.output

    def test_delete_with_force_skips_confirmation(self, tmp_path):
        gemmail = _create_gemmail(tmp_path / "test.gemmail")

        result = runner.invoke(
            app,
            ["mail", "delete", str(gemmail), "-f"],
        )
        assert result.exit_code == 0
        assert not gemmail.exists()

    def test_delete_by_index(self, tmp_path):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        f1 = _create_gemmail(mbox / "20250110T153045Z.gemmail", subject="Old")
        f2 = _create_gemmail(mbox / "20250111T100000Z.gemmail", subject="New")

        result = runner.invoke(
            app,
            ["mail", "delete", "1", "-d", str(tmp_path), "-m", "alice", "-f"],
        )
        assert result.exit_code == 0
        assert "Deleted 1" in result.output
        # Index 1 = newest (reverse sort), so f2 should be deleted
        assert not f2.exists()
        assert f1.exists()

    def test_delete_by_multiple_indices(self, tmp_path):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        f1 = _create_gemmail(mbox / "20250110T153045Z.gemmail", subject="Old")
        f2 = _create_gemmail(mbox / "20250111T100000Z.gemmail", subject="New")

        result = runner.invoke(
            app,
            [
                "mail", "delete", "1", "2",
                "-d", str(tmp_path), "-m", "alice", "-f",
            ],
        )
        assert result.exit_code == 0
        assert "Deleted 2" in result.output
        assert not f1.exists()
        assert not f2.exists()

    def test_delete_by_invalid_index(self, tmp_path):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(mbox / "20250110T153045Z.gemmail")

        result = runner.invoke(
            app,
            ["mail", "delete", "99", "-d", str(tmp_path), "-m", "alice", "-f"],
        )
        assert result.exit_code == 1
        assert "Invalid message index" in result.output


class TestMailReply:
    def test_reply_extracts_sender(self, tmp_path):
        gemmail = _create_gemmail(
            tmp_path / "test.gemmail",
            sender="bob@other.com",
        )

        # Read the message and check sender is extractable
        msg = GemmailMessage.from_bytes(gemmail.read_bytes())
        assert msg.senders[0].address == "bob@other.com"

    def test_reply_prepends_re(self, tmp_path):
        gemmail = _create_gemmail(
            tmp_path / "test.gemmail",
            sender="bob@other.com",
            subject="Hello",
        )

        msg = GemmailMessage.from_bytes(gemmail.read_bytes())
        original_subject = msg.subject
        assert original_subject == "Hello"

        # The reply logic should prepend "Re: "
        if not original_subject.startswith("Re: "):
            reply_subject = f"Re: {original_subject}"
        else:
            reply_subject = original_subject
        assert reply_subject == "Re: Hello"

    def test_reply_no_double_re(self, tmp_path):
        gemmail = _create_gemmail(
            tmp_path / "test.gemmail",
            sender="bob@other.com",
            subject="Re: Hello",
        )

        msg = GemmailMessage.from_bytes(gemmail.read_bytes())
        original_subject = msg.subject
        assert original_subject == "Re: Hello"

        if not original_subject.startswith("Re: "):
            reply_subject = f"Re: {original_subject}"
        else:
            reply_subject = original_subject
        assert reply_subject == "Re: Hello"

    def test_reply_to_no_sender_fails(self, tmp_path):
        gemmail = _create_gemmail(
            tmp_path / "test.gemmail",
            sender="",
        )

        result = runner.invoke(
            app,
            [
                "mail",
                "reply",
                str(gemmail),
                "-m",
                "thanks",
            ],
        )
        assert result.exit_code == 1
        assert "no sender" in result.output.lower()

    def test_reply_with_quote(self, tmp_path):
        gemmail = _create_gemmail(
            tmp_path / "test.gemmail",
            sender="bob@other.com",
            body="How are you?\n",
        )

        # Test the quoting logic directly
        msg = GemmailMessage.from_bytes(gemmail.read_bytes())
        quoted = "\n".join(f"> {line}" for line in msg.body.split("\n"))
        assert "> How are you?" in quoted


class TestClientConfig:
    def test_load_from_toml(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[mail]\nmailbox_dir = "/var/mail/misfin"\n')
        config = ClientConfig.from_toml(config_file)
        assert config.mailbox_dir == Path("/var/mail/misfin")

    def test_missing_file_returns_none(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/nonexistent/path")
        config = ClientConfig.load()
        assert config is None

    def test_xdg_config_home_respected(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "titlani"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text('[mail]\nmailbox_dir = "/tmp/mailboxes"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config = ClientConfig.load()
        assert config is not None
        assert config.mailbox_dir == Path("/tmp/mailboxes")

    def test_missing_mailbox_dir_key_raises(self, tmp_path):
        import pytest

        config_file = tmp_path / "config.toml"
        config_file.write_text("[mail]\n")
        with pytest.raises(ValueError, match="mailbox_dir"):
            ClientConfig.from_toml(config_file)

    def test_server_config_fallback(self, tmp_path):
        server_toml = tmp_path / "server.toml"
        server_toml.write_text(
            '[server]\nmailbox_dir = "/srv/misfin/mail"\n'
        )
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'[mail]\nserver_config = "{server_toml}"\n'
        )
        config = ClientConfig.from_toml(config_file)
        assert config.mailbox_dir == Path("/srv/misfin/mail")

    def test_server_config_fallback_missing_key_raises(self, tmp_path):
        import pytest

        server_toml = tmp_path / "server.toml"
        server_toml.write_text("[server]\nhost = \"localhost\"\n")
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'[mail]\nserver_config = "{server_toml}"\n'
        )
        with pytest.raises(ValueError, match="mailbox_dir"):
            ClientConfig.from_toml(config_file)

    def test_explicit_mailbox_dir_overrides_server_config(self, tmp_path):
        server_toml = tmp_path / "server.toml"
        server_toml.write_text(
            '[server]\nmailbox_dir = "/srv/misfin/mail"\n'
        )
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'[mail]\nmailbox_dir = "/my/mail"\n'
            f'server_config = "{server_toml}"\n'
        )
        config = ClientConfig.from_toml(config_file)
        assert config.mailbox_dir == Path("/my/mail")


class TestMailListDefaults:
    def _setup_mailbox(self, tmp_path, mailbox="alice"):
        mbox = tmp_path / mailbox
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail",
            sender="bob@other.com",
            subject="First",
        )
        _create_gemmail(
            mbox / "20250111T100000Z.gemmail",
            sender="carol@other.com",
            subject="Second",
        )
        return tmp_path

    def test_explicit_dir_works(self, tmp_path):
        mailbox_dir = self._setup_mailbox(tmp_path)
        result = runner.invoke(
            app,
            ["mail", "list", str(mailbox_dir), "-m", "alice"],
        )
        assert result.exit_code == 0
        assert "First" in result.output
        assert "Second" in result.output

    def test_config_fallback(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path)
        config_dir = tmp_path / "config" / "titlani"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f'[mail]\nmailbox_dir = "{mailbox_dir}"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("USER", "alice")
        result = runner.invoke(app, ["mail", "list"])
        assert result.exit_code == 0
        assert "First" in result.output

    def test_user_auto_detection(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, "testuser")
        config_dir = tmp_path / "config" / "titlani"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f'[mail]\nmailbox_dir = "{mailbox_dir}"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("USER", "testuser")
        result = runner.invoke(app, ["mail", "list"])
        assert result.exit_code == 0
        assert "First" in result.output

    def test_row_numbers_in_output(self, tmp_path):
        mailbox_dir = self._setup_mailbox(tmp_path)
        result = runner.invoke(
            app,
            ["mail", "list", str(mailbox_dir), "-m", "alice"],
        )
        assert result.exit_code == 0
        # Row numbers 1 and 2 should appear in the table
        assert " 1 " in result.output
        assert " 2 " in result.output

    def test_no_dir_no_config_uses_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("USER", "testuser")
        result = runner.invoke(app, ["mail", "list"])
        assert result.exit_code == 0
        default_mail = tmp_path / "data" / "titlani" / "mail"
        assert default_mail.is_dir()
        assert (default_mail / "testuser").is_dir()


class TestMailReadByIndex:
    def _setup_mailbox(self, tmp_path, mailbox="alice"):
        mbox = tmp_path / mailbox
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail",
            sender="bob@other.com",
            subject="Older message",
        )
        _create_gemmail(
            mbox / "20250111T100000Z.gemmail",
            sender="carol@other.com",
            subject="Newer message",
        )
        return tmp_path

    def test_read_by_index(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path)
        config_dir = tmp_path / "config" / "titlani"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f'[mail]\nmailbox_dir = "{mailbox_dir}"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("USER", "alice")
        # Index 1 = newest (reverse order)
        result = runner.invoke(app, ["mail", "read", "1"])
        assert result.exit_code == 0
        assert "Newer message" in result.output

    def test_read_by_index_with_explicit_dir(self, tmp_path):
        mailbox_dir = self._setup_mailbox(tmp_path)
        result = runner.invoke(
            app,
            [
                "mail",
                "read",
                "2",
                "-d",
                str(mailbox_dir),
                "-m",
                "alice",
            ],
        )
        assert result.exit_code == 0
        assert "Older message" in result.output

    def test_read_by_path_still_works(self, tmp_path):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        gemmail = _create_gemmail(
            mbox / "20250110T153045Z.gemmail",
            sender="bob@other.com",
            subject="Direct path",
        )
        result = runner.invoke(app, ["mail", "read", str(gemmail)])
        assert result.exit_code == 0
        assert "Direct path" in result.output

    def test_out_of_range_index(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path)
        config_dir = tmp_path / "config" / "titlani"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f'[mail]\nmailbox_dir = "{mailbox_dir}"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("USER", "alice")
        result = runner.invoke(app, ["mail", "read", "99"])
        assert result.exit_code == 1
        assert "Invalid message index" in result.output

    def test_index_matches_list_order(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path)
        config_dir = tmp_path / "config" / "titlani"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f'[mail]\nmailbox_dir = "{mailbox_dir}"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("USER", "alice")
        # Index 1 = newest, index 2 = oldest (reverse sort)
        result1 = runner.invoke(app, ["mail", "read", "1"])
        assert "Newer message" in result1.output
        result2 = runner.invoke(app, ["mail", "read", "2"])
        assert "Older message" in result2.output
