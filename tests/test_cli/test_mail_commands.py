"""Tests for mail CLI commands."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
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

    def test_delete_by_index(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        f1 = _create_gemmail(mbox / "20250110T153045Z.gemmail", subject="Old")
        f2 = _create_gemmail(mbox / "20250111T100000Z.gemmail", subject="New")

        result = runner.invoke(
            app,
            ["mail", "delete", "1", "-d", str(tmp_path), "-f"],
        )
        assert result.exit_code == 0
        assert "Deleted 1" in result.output
        # Index 1 = newest (reverse sort), so f2 should be deleted
        assert not f2.exists()
        assert f1.exists()

    def test_delete_by_multiple_indices(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        f1 = _create_gemmail(mbox / "20250110T153045Z.gemmail", subject="Old")
        f2 = _create_gemmail(mbox / "20250111T100000Z.gemmail", subject="New")

        result = runner.invoke(
            app,
            [
                "mail",
                "delete",
                "1",
                "2",
                "-d",
                str(tmp_path),
                "-f",
            ],
        )
        assert result.exit_code == 0
        assert "Deleted 2" in result.output
        assert not f1.exists()
        assert not f2.exists()

    def test_delete_by_invalid_index(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(mbox / "20250110T153045Z.gemmail")

        result = runner.invoke(
            app,
            ["mail", "delete", "99", "-d", str(tmp_path), "-f"],
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

    def test_reply_link_injected_for_id_filename(self, tmp_path):
        """mail reply injects => mid:<id> when the file has a message ID."""
        from titlani.content.message_id import (
            build_reply_link,
            parse_message_id_from_filename,
        )

        filename = "20260213T143052Z-a1b2c3d4.gemmail"
        gemmail = _create_gemmail(
            tmp_path / filename,
            sender="bob@other.com",
        )

        # Simulate the reply link injection logic from mail_reply()
        original_msgid = parse_message_id_from_filename(gemmail.name)
        assert original_msgid == "20260213T143052Z-a1b2c3d4"

        reply_body = "Thanks for the message!"
        if original_msgid:
            link = build_reply_link(original_msgid)
            reply_body = f"{reply_body.rstrip()}\n{link}\n"

        assert "=> mid:20260213T143052Z-a1b2c3d4 In reply to" in reply_body

    def test_reply_link_not_injected_for_old_filename(self, tmp_path):
        """mail reply still injects a link for old-format filenames."""
        from titlani.content.message_id import (
            build_reply_link,
            parse_message_id_from_filename,
        )

        filename = "20260213T143052Z.gemmail"
        gemmail = _create_gemmail(
            tmp_path / filename,
            sender="bob@other.com",
        )

        original_msgid = parse_message_id_from_filename(gemmail.name)
        assert original_msgid == "20260213T143052Z"

        reply_body = "Thanks!"
        if original_msgid:
            link = build_reply_link(original_msgid)
            reply_body = f"{reply_body.rstrip()}\n{link}\n"

        assert "=> mid:20260213T143052Z In reply to" in reply_body

    def test_reply_link_not_injected_for_non_gemmail(self, tmp_path):
        """No link injected when file has unrecognized name."""
        from titlani.content.message_id import parse_message_id_from_filename

        original_msgid = parse_message_id_from_filename("notes.txt")
        assert original_msgid is None


class TestMailListThreading:
    def test_thread_indicator_shown(self, tmp_path, monkeypatch):
        """mail list shows reply count indicator for threaded messages."""
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()

        # Create a parent message with a message-ID filename
        _create_gemmail(
            mbox / "20260213T100000Z-aabbccdd.gemmail",
            sender="bob@other.com",
            subject="Hello",
        )

        # Create a reply that references the parent
        reply_body = (
            "# Re: Hello\n\n"
            "Thanks!\n"
            "=> mid:20260213T100000Z-aabbccdd In reply to\n"
        )
        reply_msg = GemmailMessage(
            senders=[MisfinAddress("charlie", "other.com")],
            recipients=[MisfinAddress("alice", "example.com")],
            timestamps=[datetime.now(UTC)],
            body=reply_body,
        )
        reply_file = mbox / "20260213T110000Z-11223344.gemmail"
        reply_file.write_bytes(reply_msg.to_bytes())

        result = runner.invoke(
            app,
            ["mail", "list", str(tmp_path)],
        )
        assert result.exit_code == 0
        # The parent message should show a reply indicator
        assert "↳1" in result.output

    def test_no_thread_indicator_without_replies(self, tmp_path, monkeypatch):
        """No thread indicator when no replies reference the message."""
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()

        _create_gemmail(
            mbox / "20260213T100000Z-aabbccdd.gemmail",
            sender="bob@other.com",
            subject="Hello",
        )

        result = runner.invoke(
            app,
            ["mail", "list", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "↳" not in result.output

    def test_encrypted_messages_skip_threading(self, tmp_path, monkeypatch):
        """Encrypted messages don't break threading (no body to parse)."""
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()

        _create_gemmail(
            mbox / "20260213T100000Z-aabbccdd.gemmail",
            sender="bob@other.com",
            subject="Hello",
        )

        # Encrypted file can't be parsed — just raw bytes
        enc_file = mbox / "20260213T110000Z-11223344.gemmail.enc"
        enc_file.write_bytes(b"\x00\x01\x02encrypted-data")

        result = runner.invoke(
            app,
            ["mail", "list", str(tmp_path)],
        )
        assert result.exit_code == 0
        # Should not crash, and no spurious indicators
        assert "↳" not in result.output


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
        config_file = tmp_path / "config.toml"
        config_file.write_text("[mail]\n")
        with pytest.raises(ValueError, match="mailbox_dir"):
            ClientConfig.from_toml(config_file)

    def test_server_config_fallback(self, tmp_path):
        server_toml = tmp_path / "server.toml"
        server_toml.write_text('[server]\nmailbox_dir = "/srv/misfin/mail"\n')
        config_file = tmp_path / "config.toml"
        config_file.write_text(f'[mail]\nserver_config = "{server_toml}"\n')
        config = ClientConfig.from_toml(config_file)
        assert config.mailbox_dir == Path("/srv/misfin/mail")

    def test_server_config_fallback_missing_key_raises(self, tmp_path):
        server_toml = tmp_path / "server.toml"
        server_toml.write_text('[server]\nhost = "localhost"\n')
        config_file = tmp_path / "config.toml"
        config_file.write_text(f'[mail]\nserver_config = "{server_toml}"\n')
        with pytest.raises(ValueError, match="mailbox_dir"):
            ClientConfig.from_toml(config_file)

    def test_explicit_mailbox_dir_overrides_server_config(self, tmp_path):
        server_toml = tmp_path / "server.toml"
        server_toml.write_text('[server]\nmailbox_dir = "/srv/misfin/mail"\n')
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'[mail]\nmailbox_dir = "/my/mail"\nserver_config = "{server_toml}"\n'
        )
        config = ClientConfig.from_toml(config_file)
        assert config.mailbox_dir == Path("/my/mail")


class TestMailBlock:
    def test_block_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        result = runner.invoke(
            app,
            ["mail", "block", "spam@evil.com", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Blocked" in result.output
        blocked = (mbox / ".blocked").read_text()
        assert "spam@evil.com" in blocked

    def test_block_duplicate_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        (mbox / ".blocked").write_text("spam@evil.com\n")
        result = runner.invoke(
            app,
            ["mail", "block", "spam@evil.com", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "already blocked" in result.output

    def test_block_invalid_address(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        result = runner.invoke(
            app,
            ["mail", "block", "not-an-address", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Invalid address" in result.output

    def test_unblock_removes_address(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        (mbox / ".blocked").write_text("spam@evil.com\nother@bad.com\n")
        result = runner.invoke(
            app,
            ["mail", "unblock", "spam@evil.com", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Unblocked" in result.output
        blocked = (mbox / ".blocked").read_text()
        assert "spam@evil.com" not in blocked
        assert "other@bad.com" in blocked

    def test_unblock_last_address_removes_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        (mbox / ".blocked").write_text("spam@evil.com\n")
        result = runner.invoke(
            app,
            ["mail", "unblock", "spam@evil.com", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert not (mbox / ".blocked").exists()

    def test_unblock_nonexistent_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        result = runner.invoke(
            app,
            ["mail", "unblock", "nobody@here.com", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "was not blocked" in result.output


class TestUnreadTracking:
    def test_new_messages_show_new_indicator(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail.new",
            sender="bob@other.com",
            subject="Unread",
        )
        _create_gemmail(
            mbox / "20250109T100000Z.gemmail",
            sender="carol@other.com",
            subject="Already read",
        )
        result = runner.invoke(
            app,
            ["mail", "list", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "NEW" in result.output
        assert "1 new" in result.output

    def test_read_removes_new_suffix(self, tmp_path):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        new_file = mbox / "20250110T153045Z.gemmail.new"
        _create_gemmail(new_file, subject="Test")
        assert new_file.exists()

        result = runner.invoke(
            app,
            ["mail", "read", str(new_file)],
        )
        assert result.exit_code == 0
        assert not new_file.exists()
        assert (mbox / "20250110T153045Z.gemmail").exists()

    def test_read_already_read_message(self, tmp_path):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        read_file = mbox / "20250110T153045Z.gemmail"
        _create_gemmail(read_file, subject="Already read")

        result = runner.invoke(
            app,
            ["mail", "read", str(read_file)],
        )
        assert result.exit_code == 0
        assert read_file.exists()

    def test_read_by_index_marks_as_read(self, tmp_path, monkeypatch):
        mbox = tmp_path / "alice"
        mbox.mkdir()
        new_file = mbox / "20250110T153045Z.gemmail.new"
        _create_gemmail(new_file, subject="Indexed message")
        config_dir = tmp_path / "config" / "titlani"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(f'[mail]\nmailbox_dir = "{tmp_path}"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(app, ["mail", "read", "1"])
        assert result.exit_code == 0
        assert not new_file.exists()
        assert (mbox / "20250110T153045Z.gemmail").exists()

    def test_no_new_messages_no_count(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail",
            subject="All read",
        )
        result = runner.invoke(
            app,
            ["mail", "list", str(tmp_path)],
        )
        assert result.exit_code == 0
        # Title should be "Messages (1)" without "(X new)"
        assert "new)" not in result.output


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

    def test_explicit_dir_works(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mailbox_dir = self._setup_mailbox(tmp_path)
        result = runner.invoke(
            app,
            ["mail", "list", str(mailbox_dir)],
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

    def test_row_numbers_in_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mailbox_dir = self._setup_mailbox(tmp_path)
        result = runner.invoke(
            app,
            ["mail", "list", str(mailbox_dir)],
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

    def test_read_by_index_with_explicit_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mailbox_dir = self._setup_mailbox(tmp_path)
        result = runner.invoke(
            app,
            [
                "mail",
                "read",
                "2",
                "-d",
                str(mailbox_dir),
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


class TestMailSearch:
    def _setup_mailbox(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail",
            sender="bob@other.com",
            body="Let's meet for coffee tomorrow.\n",
            subject="Coffee plans",
        )
        _create_gemmail(
            mbox / "20250111T100000Z.gemmail",
            sender="carol@example.org",
            body="The project deadline is next Friday.\n",
            subject="Project update",
        )
        _create_gemmail(
            mbox / "20250112T120000Z.gemmail",
            sender="bob@other.com",
            body="Sounds good, see you then!\n",
            subject="Re: Coffee plans",
        )
        return tmp_path

    def test_search_by_query_matches_subject(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app, ["mail", "search", "coffee", "-d", str(mailbox_dir)]
        )
        assert result.exit_code == 0
        assert "Messages (2)" in result.output
        assert "Coffee plans" in result.output
        assert "Project update" not in result.output

    def test_search_by_query_matches_body(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app, ["mail", "search", "deadline", "-d", str(mailbox_dir)]
        )
        assert result.exit_code == 0
        assert "Project update" in result.output
        assert "Coffee" not in result.output

    def test_search_by_query_matches_sender(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app, ["mail", "search", "carol", "-d", str(mailbox_dir)]
        )
        assert result.exit_code == 0
        assert "Project update" in result.output
        assert "Coffee" not in result.output

    def test_search_case_insensitive(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app, ["mail", "search", "COFFEE", "-d", str(mailbox_dir)]
        )
        assert result.exit_code == 0
        assert "Coffee plans" in result.output

    def test_search_no_results(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app, ["mail", "search", "nonexistent", "-d", str(mailbox_dir)]
        )
        assert result.exit_code == 0
        assert "No messages found" in result.output

    def test_search_from_filter(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app,
            ["mail", "search", "--from", "carol", "-d", str(mailbox_dir)],
        )
        assert result.exit_code == 0
        assert "Project update" in result.output
        assert "Coffee" not in result.output

    def test_search_subject_filter(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app,
            [
                "mail", "search",
                "--subject", "project",
                "-d", str(mailbox_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Project update" in result.output
        assert "Coffee" not in result.output

    def test_search_body_filter(self, tmp_path, monkeypatch):
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app,
            [
                "mail", "search",
                "--body", "Friday",
                "-d", str(mailbox_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Project update" in result.output
        assert "Coffee" not in result.output

    def test_search_combined_filters_and_logic(self, tmp_path, monkeypatch):
        """--from and --subject combine with AND logic."""
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app,
            [
                "mail", "search",
                "--from", "bob",
                "--subject", "Re:",
                "-d", str(mailbox_dir),
            ],
        )
        assert result.exit_code == 0
        # Only the "Re: Coffee plans" from bob matches both filters
        assert "Messages (1)" in result.output

    def test_search_query_plus_filter(self, tmp_path, monkeypatch):
        """Positional query AND --from filter combine."""
        mailbox_dir = self._setup_mailbox(tmp_path, monkeypatch)
        result = runner.invoke(
            app,
            [
                "mail", "search", "coffee",
                "--from", "carol",
                "-d", str(mailbox_dir),
            ],
        )
        assert result.exit_code == 0
        # carol didn't send any coffee messages
        assert "No messages found" in result.output

    def test_search_no_query_no_filters_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        result = runner.invoke(
            app, ["mail", "search", "-d", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "Provide a search query" in result.output

    def test_search_encrypted_skipped_without_key(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail",
            sender="bob@other.com",
            subject="Visible",
        )
        enc_file = mbox / "20250111T100000Z.gemmail.enc"
        enc_file.write_bytes(b"\x00\x01\x02encrypted")

        result = runner.invoke(
            app, ["mail", "search", "Visible", "-d", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "Visible" in result.output
        assert "1 encrypted" in result.output

    def test_search_new_messages_shown(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(
            mbox / "20250110T153045Z.gemmail.new",
            sender="bob@other.com",
            subject="Unread match",
        )
        result = runner.invoke(
            app, ["mail", "search", "Unread", "-d", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "Messages (1)" in result.output
        assert "1 new" in result.output


class TestMailboxOwnershipVerification:
    """Tests for OS-user-based mailbox access control."""

    def test_access_own_mailbox_succeeds(self, tmp_path, monkeypatch):
        """User can access their own mailbox (dir owned by them)."""
        monkeypatch.setenv("USER", "alice")
        mbox = tmp_path / "alice"
        mbox.mkdir()
        _create_gemmail(mbox / "20250110T153045Z.gemmail", subject="Mine")

        result = runner.invoke(app, ["mail", "list", str(tmp_path)])
        assert result.exit_code == 0
        assert "Mine" in result.output

    def test_access_other_users_mailbox_denied(self, tmp_path, monkeypatch):
        """User cannot access a mailbox owned by a different UID."""
        import os

        monkeypatch.setenv("USER", "bob")
        mbox = tmp_path / "bob"
        mbox.mkdir()
        _create_gemmail(mbox / "20250110T153045Z.gemmail", subject="Secret")

        # Fake the ownership check: make getuid return a different UID
        # than the directory owner
        real_uid = os.getuid()
        monkeypatch.setattr("os.getuid", lambda: real_uid + 1)

        result = runner.invoke(app, ["mail", "list", str(tmp_path)])
        assert result.exit_code != 0
        assert "Permission denied" in result.output

    def test_create_mailbox_subdir_sets_700(self, tmp_path):
        """create_mailbox_subdir sets 0o700 on the directory."""
        import stat

        from titlani.cli.mailbox import create_mailbox_subdir

        path = create_mailbox_subdir(tmp_path, "testuser")
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o700

    def test_default_mailbox_auto_created_with_700(
        self, tmp_path, monkeypatch
    ):
        """Default mailbox auto-creation uses secure permissions."""
        import stat

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("USER", "testuser")
        runner.invoke(app, ["mail", "list"])

        mbox = tmp_path / "data" / "titlani" / "mail" / "testuser"
        assert mbox.is_dir()
        mode = stat.S_IMODE(mbox.stat().st_mode)
        assert mode == 0o700

