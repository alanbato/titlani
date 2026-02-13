"""Tests for mailing list CLI commands."""

from typer.testing import CliRunner

from titlani.__main__ import app

runner = CliRunner()


class TestMailListCreate:
    def test_creates_list_directory(self, tmp_path):
        result = runner.invoke(
            app,
            ["mail", "list-create", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Created" in result.output
        list_path = tmp_path / "announce"
        assert list_path.is_dir()
        assert (list_path / "subscribers.txt").exists()

    def test_subscribers_file_has_comments(self, tmp_path):
        runner.invoke(
            app,
            ["mail", "list-create", "announce", "-d", str(tmp_path)],
        )
        content = (tmp_path / "announce" / "subscribers.txt").read_text()
        assert content.startswith("#")

    def test_rejects_existing_mailbox(self, tmp_path):
        (tmp_path / "announce").mkdir()
        result = runner.invoke(
            app,
            ["mail", "list-create", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_rejects_invalid_name(self, tmp_path):
        result = runner.invoke(
            app,
            ["mail", "list-create", "my list!", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Invalid" in result.output

    def test_accepts_dots_dashes_underscores(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "mail",
                "list-create",
                "my-list_v2.0",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "my-list_v2.0").is_dir()


class TestMailListSubscribers:
    def test_shows_subscribers(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text(
            "alice@example.com\nbob@other.com\n"
        )
        result = runner.invoke(
            app,
            ["mail", "list-subscribers", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "bob@other.com" in result.output
        assert "2" in result.output

    def test_empty_list(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("# empty\n")
        result = runner.invoke(
            app,
            ["mail", "list-subscribers", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "No subscribers" in result.output

    def test_nonexistent_list(self, tmp_path):
        result = runner.invoke(
            app,
            ["mail", "list-subscribers", "nope", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_not_a_mailing_list(self, tmp_path):
        (tmp_path / "alice").mkdir()
        result = runner.invoke(
            app,
            ["mail", "list-subscribers", "alice", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Not a mailing list" in result.output


class TestMailListAdd:
    def test_adds_subscriber(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("# subscribers\n")
        result = runner.invoke(
            app,
            [
                "mail",
                "list-add",
                "announce",
                "alice@example.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Added" in result.output
        content = (list_path / "subscribers.txt").read_text()
        assert "alice@example.com" in content

    def test_rejects_duplicate(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("alice@example.com\n")
        result = runner.invoke(
            app,
            [
                "mail",
                "list-add",
                "announce",
                "alice@example.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "already subscribed" in result.output

    def test_rejects_invalid_address(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("")
        result = runner.invoke(
            app,
            [
                "mail",
                "list-add",
                "announce",
                "not-an-address",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
        assert "Invalid" in result.output

    def test_rejects_non_list_mailbox(self, tmp_path):
        (tmp_path / "alice").mkdir()
        result = runner.invoke(
            app,
            [
                "mail",
                "list-add",
                "alice",
                "bob@other.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
        assert "Not a mailing list" in result.output


class TestMailListRemove:
    def test_removes_subscriber(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text(
            "alice@example.com\nbob@other.com\n"
        )
        result = runner.invoke(
            app,
            [
                "mail",
                "list-remove",
                "announce",
                "alice@example.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        content = (list_path / "subscribers.txt").read_text()
        assert "alice@example.com" not in content
        assert "bob@other.com" in content

    def test_preserves_comments(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text(
            "# List subscribers\nalice@example.com\nbob@other.com\n"
        )
        result = runner.invoke(
            app,
            [
                "mail",
                "list-remove",
                "announce",
                "alice@example.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        content = (list_path / "subscribers.txt").read_text()
        assert "# List subscribers" in content
        assert "bob@other.com" in content

    def test_nonexistent_subscriber(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("alice@example.com\n")
        result = runner.invoke(
            app,
            [
                "mail",
                "list-remove",
                "announce",
                "nobody@here.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "not subscribed" in result.output
