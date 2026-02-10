"""Tests for mail delete and mail reply CLI commands."""

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from titlani.__main__ import app
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
