"""Tests for admin CLI commands."""

import os
import stat
from pathlib import Path

from typer.testing import CliRunner

from titlani.__main__ import app

runner = CliRunner()


class TestAdminFixperms:
    def _make_mailbox(self, parent: Path, name: str, mode: int = 0o700) -> Path:
        mbox = parent / name
        mbox.mkdir()
        os.chmod(mbox, mode)
        return mbox

    def test_no_subdirectories(self, tmp_path):
        result = runner.invoke(
            app, ["admin", "fixperms", "-d", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "No mailbox subdirectories" in result.output

    def test_all_permissions_correct(self, tmp_path):
        self._make_mailbox(tmp_path, "alice", 0o700)
        self._make_mailbox(tmp_path, "bob", 0o700)

        result = runner.invoke(
            app, ["admin", "fixperms", "-d", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "All mailbox permissions are correct" in result.output

    def test_shows_table_with_problems(self, tmp_path):
        self._make_mailbox(tmp_path, "alice", 0o700)
        self._make_mailbox(tmp_path, "bob", 0o755)

        result = runner.invoke(
            app, ["admin", "fixperms", "-d", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "bob" in result.output
        assert "0o755" in result.output
        assert "0o700" in result.output

    def test_dry_run_does_not_change(self, tmp_path):
        mbox = self._make_mailbox(tmp_path, "alice", 0o755)

        result = runner.invoke(
            app, ["admin", "fixperms", "-d", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output
        # Permissions unchanged
        mode = stat.S_IMODE(mbox.stat().st_mode)
        assert mode == 0o755

    def test_fixes_permissions(self, tmp_path):
        mbox = self._make_mailbox(tmp_path, "alice", 0o755)

        result = runner.invoke(
            app,
            ["admin", "fixperms", "-d", str(tmp_path)],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "Fixed 1" in result.output
        mode = stat.S_IMODE(mbox.stat().st_mode)
        assert mode == 0o700

    def test_cancel_does_not_change(self, tmp_path):
        mbox = self._make_mailbox(tmp_path, "alice", 0o755)

        result = runner.invoke(
            app,
            ["admin", "fixperms", "-d", str(tmp_path)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Cancelled" in result.output
        mode = stat.S_IMODE(mbox.stat().st_mode)
        assert mode == 0o755

    def test_ownership_mismatch_shown(self, tmp_path, monkeypatch):
        """When dir owner != dir name, the table shows a warning."""
        import pwd

        mbox = self._make_mailbox(tmp_path, "nobody", 0o700)
        # The dir is owned by the test user, not "nobody", so
        # the ownership mismatch will be reported
        real_owner = pwd.getpwuid(mbox.stat().st_uid).pw_name
        if real_owner != "nobody":
            result = runner.invoke(
                app, ["admin", "fixperms", "-d", str(tmp_path)]
            )
            assert result.exit_code == 0
            assert f"owned by {real_owner}" in result.output

    def test_fixes_multiple_directories(self, tmp_path):
        m1 = self._make_mailbox(tmp_path, "alice", 0o777)
        m2 = self._make_mailbox(tmp_path, "bob", 0o750)
        self._make_mailbox(tmp_path, "carol", 0o700)

        result = runner.invoke(
            app,
            ["admin", "fixperms", "-d", str(tmp_path)],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "Fixed 2" in result.output
        assert stat.S_IMODE(m1.stat().st_mode) == 0o700
        assert stat.S_IMODE(m2.stat().st_mode) == 0o700
