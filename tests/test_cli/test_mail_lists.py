"""Tests for mailing list CLI commands."""

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from titlani.__main__ import app
from titlani.server.lists import SUBSCRIPTION_DB_FILE
from titlani.server.subscription import SubscriptionTokenStore

runner = CliRunner()


class TestMailListCreate:
    def test_creates_list_directory(self, tmp_path):
        result = runner.invoke(
            app,
            ["list", "create", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Created" in result.output
        list_path = tmp_path / "announce"
        assert list_path.is_dir()
        assert (list_path / "subscribers.txt").exists()

    def test_subscribers_file_has_comments(self, tmp_path):
        runner.invoke(
            app,
            ["list", "create", "announce", "-d", str(tmp_path)],
        )
        content = (tmp_path / "announce" / "subscribers.txt").read_text()
        assert content.startswith("#")

    def test_rejects_existing_mailbox(self, tmp_path):
        (tmp_path / "announce").mkdir()
        result = runner.invoke(
            app,
            ["list", "create", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_rejects_invalid_name(self, tmp_path):
        result = runner.invoke(
            app,
            ["list", "create", "my list!", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Invalid" in result.output

    def test_accepts_dots_dashes_underscores(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "list",
                "create",
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
        (list_path / "subscribers.txt").write_text("alice@example.com\nbob@other.com\n")
        result = runner.invoke(
            app,
            ["list", "subscribers", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        assert "bob@other.com" in result.output
        assert "confirmed" in result.output.lower()

    def test_shows_pending_status(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("alice@example.com\n")
        db_path = tmp_path / SUBSCRIPTION_DB_FILE
        with SubscriptionTokenStore(db_path) as store:
            store.create_token("announce", "bob@other.com")

        result = runner.invoke(
            app,
            ["list", "subscribers", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "confirmed" in result.output.lower()
        assert "pending" in result.output.lower()
        assert "2" in result.output  # total count

    def test_empty_list(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("# empty\n")
        result = runner.invoke(
            app,
            ["list", "subscribers", "announce", "-d", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "No subscribers" in result.output

    def test_nonexistent_list(self, tmp_path):
        result = runner.invoke(
            app,
            ["list", "subscribers", "nope", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_not_a_mailing_list(self, tmp_path):
        (tmp_path / "alice").mkdir()
        result = runner.invoke(
            app,
            ["list", "subscribers", "alice", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Not a mailing list" in result.output


class TestMailListAdd:
    def test_adds_subscriber_no_verify(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("# subscribers\n")
        result = runner.invoke(
            app,
            [
                "list",
                "add",
                "announce",
                "alice@example.com",
                "-d",
                str(tmp_path),
                "--no-verify",
            ],
        )
        assert result.exit_code == 0
        assert "Added" in result.output
        content = (list_path / "subscribers.txt").read_text()
        assert "alice@example.com" in content

    def test_add_with_verification(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("# subscribers\n")

        with patch(
            "titlani.cli.commands.list._send_verification",
            new_callable=AsyncMock,
        ):
            result = runner.invoke(
                app,
                [
                    "list",
                    "add",
                    "announce",
                    "alice@example.com",
                    "-d",
                    str(tmp_path),
                    "-H",
                    "example.com",
                ],
            )
        assert result.exit_code == 0
        assert "pending" in result.output.lower()
        # Should NOT be in subscribers.txt yet
        content = (list_path / "subscribers.txt").read_text()
        assert "alice@example.com" not in content
        # Should be in pending DB
        db_path = tmp_path / SUBSCRIPTION_DB_FILE
        assert db_path.exists()
        with SubscriptionTokenStore(db_path) as store:
            assert store.is_pending("announce", "alice@example.com")

    def test_rejects_duplicate(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("alice@example.com\n")
        result = runner.invoke(
            app,
            [
                "list",
                "add",
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
                "list",
                "add",
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
                "list",
                "add",
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
        (list_path / "subscribers.txt").write_text("alice@example.com\nbob@other.com\n")
        result = runner.invoke(
            app,
            [
                "list",
                "remove",
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
                "list",
                "remove",
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
                "list",
                "remove",
                "announce",
                "nobody@here.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "not subscribed" in result.output

    def test_remove_cleans_up_pending(self, tmp_path):
        list_path = tmp_path / "announce"
        list_path.mkdir()
        (list_path / "subscribers.txt").write_text("alice@example.com\n")
        db_path = tmp_path / SUBSCRIPTION_DB_FILE
        with SubscriptionTokenStore(db_path) as store:
            store.create_token("announce", "alice@example.com")

        result = runner.invoke(
            app,
            [
                "list",
                "remove",
                "announce",
                "alice@example.com",
                "-d",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        with SubscriptionTokenStore(db_path) as store:
            assert not store.is_pending("announce", "alice@example.com")
