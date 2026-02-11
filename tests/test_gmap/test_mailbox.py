"""Tests for GMAP mailbox index operations."""

import json
from datetime import UTC, datetime
from pathlib import Path

from titlani.gmap.mailbox import GmapMailbox, _filename_to_msgid


def _create_gemmail(mailbox_path: Path, msgid: str, content: str = "") -> Path:
    """Create a minimal .gemmail file in the mailbox directory."""
    if not content:
        content = (
            "sender@example.com\n"
            "recipient@example.com\n"
            "2026-02-11T12:00:00Z\n"
            "# Test message\n"
            "Hello\n"
        )
    filepath = mailbox_path / f"{msgid}.gemmail"
    filepath.write_text(content)
    return filepath


class TestFilenameMsgid:
    def test_gemmail(self):
        assert _filename_to_msgid("20260211T143052Z.gemmail") == "20260211T143052Z"

    def test_gemmail_new(self):
        assert _filename_to_msgid("20260211T143052Z.gemmail.new") == "20260211T143052Z"

    def test_gemmail_enc(self):
        assert _filename_to_msgid("20260211T143052Z.gemmail.enc") == "20260211T143052Z"

    def test_gemmail_enc_new(self):
        result = _filename_to_msgid("20260211T143052Z.gemmail.enc.new")
        assert result == "20260211T143052Z"

    def test_invalid_extension(self):
        assert _filename_to_msgid("test.txt") is None

    def test_invalid_format(self):
        assert _filename_to_msgid("not-a-timestamp.gemmail") is None

    def test_empty(self):
        assert _filename_to_msgid("") is None


class TestGmapMailboxLoad:
    def test_load_empty_mailbox(self, tmp_path):
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        assert mbox.messages == {}

    def test_load_existing_index(self, tmp_path):
        index = {
            "version": 1,
            "messages": {
                "20260211T120000Z": {
                    "tags": ["Inbox", "Unread"],
                    "timestamp": "2026-02-11T12:00:00Z",
                    "filename": "20260211T120000Z.gemmail",
                }
            },
        }
        (tmp_path / ".gmap.json").write_text(json.dumps(index))

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        assert "20260211T120000Z" in mbox.messages
        assert mbox.messages["20260211T120000Z"].tags == {"Inbox", "Unread"}

    def test_load_corrupt_index(self, tmp_path):
        (tmp_path / ".gmap.json").write_text("not json{{{")
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        assert mbox.messages == {}


class TestGmapMailboxSave:
    def test_save_creates_file(self, tmp_path):
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.save()
        assert (tmp_path / ".gmap.json").exists()
        data = json.loads((tmp_path / ".gmap.json").read_text())
        assert data["version"] == 1

    def test_save_roundtrip(self, tmp_path):
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        _create_gemmail(tmp_path, "20260211T120000Z")
        mbox.sync_filesystem()
        mbox.save()

        mbox2 = GmapMailbox(tmp_path)
        mbox2.load()
        assert "20260211T120000Z" in mbox2.messages
        assert mbox2.messages["20260211T120000Z"].tags == {"Inbox", "Unread"}


class TestGmapMailboxSync:
    def test_sync_discovers_new_files(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")
        _create_gemmail(tmp_path, "20260211T130000Z")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        modified = mbox.sync_filesystem()

        assert modified is True
        assert len(mbox.messages) == 2
        assert "20260211T120000Z" in mbox.messages
        assert "20260211T130000Z" in mbox.messages

    def test_sync_auto_tags_inbox_unread(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        entry = mbox.messages["20260211T120000Z"]
        assert "Inbox" in entry.tags
        assert "Unread" in entry.tags

    def test_sync_ignores_known_files(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()
        modified = mbox.sync_filesystem()

        assert modified is False

    def test_sync_removes_deleted_files(self, tmp_path):
        path = _create_gemmail(tmp_path, "20260211T120000Z")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()
        assert len(mbox.messages) == 1

        path.unlink()
        modified = mbox.sync_filesystem()

        assert modified is True
        assert len(mbox.messages) == 0

    def test_sync_discovers_unread_files(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")
        # Rename to .new to simulate server delivery
        src = tmp_path / "20260211T120000Z.gemmail"
        src.rename(tmp_path / "20260211T120000Z.gemmail.new")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        assert "20260211T120000Z" in mbox.messages
        entry = mbox.messages["20260211T120000Z"]
        assert "Inbox" in entry.tags
        assert "Unread" in entry.tags

    def test_sync_preserves_tags_after_rename(self, tmp_path):
        """When CLI marks a .new message as read, GMAP should
        update the filename but keep existing tags."""
        # Simulate server delivery
        _create_gemmail(tmp_path, "20260211T120000Z")
        src = tmp_path / "20260211T120000Z.gemmail"
        src.rename(tmp_path / "20260211T120000Z.gemmail.new")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        # User reads via GMAP → removes Unread tag
        mbox.remove_tag("20260211T120000Z", "Unread")
        mbox.add_tag("20260211T120000Z", "Important")
        mbox.save()

        # CLI reads → renames .new to .gemmail
        new_path = tmp_path / "20260211T120000Z.gemmail.new"
        new_path.rename(tmp_path / "20260211T120000Z.gemmail")

        # Next GMAP sync should update filename but keep tags
        mbox2 = GmapMailbox(tmp_path)
        mbox2.load()
        mbox2.sync_filesystem()

        entry = mbox2.messages["20260211T120000Z"]
        assert entry.filename == "20260211T120000Z.gemmail"
        assert "Important" in entry.tags
        assert "Unread" not in entry.tags

    def test_sync_discovers_encrypted_unread_files(self, tmp_path):
        (tmp_path / "20260211T120000Z.gemmail.enc.new").write_bytes(b"encrypted")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        assert "20260211T120000Z" in mbox.messages
        assert mbox.is_encrypted("20260211T120000Z")

    def test_sync_discovers_encrypted_files(self, tmp_path):
        (tmp_path / "20260211T120000Z.gemmail.enc").write_bytes(b"encrypted")

        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        assert "20260211T120000Z" in mbox.messages
        assert mbox.is_encrypted("20260211T120000Z")


class TestGmapMailboxTags:
    def _make_indexed_mbox(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")
        _create_gemmail(tmp_path, "20260211T130000Z")
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()
        return mbox

    def test_add_tag(self, tmp_path):
        mbox = self._make_indexed_mbox(tmp_path)
        assert mbox.add_tag("20260211T120000Z", "Archive")
        assert "Archive" in mbox.messages["20260211T120000Z"].tags

    def test_add_tag_nonexistent_message(self, tmp_path):
        mbox = self._make_indexed_mbox(tmp_path)
        assert not mbox.add_tag("nonexistent", "Archive")

    def test_add_invalid_tag(self, tmp_path):
        mbox = self._make_indexed_mbox(tmp_path)
        assert not mbox.add_tag("20260211T120000Z", "bad tag!")

    def test_remove_tag(self, tmp_path):
        mbox = self._make_indexed_mbox(tmp_path)
        assert "Inbox" in mbox.messages["20260211T120000Z"].tags
        assert mbox.remove_tag("20260211T120000Z", "Inbox")
        assert "Inbox" not in mbox.messages["20260211T120000Z"].tags

    def test_remove_tag_not_present(self, tmp_path):
        mbox = self._make_indexed_mbox(tmp_path)
        assert mbox.remove_tag("20260211T120000Z", "Archive")


class TestGmapMailboxList:
    def _make_mbox_with_tags(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")
        _create_gemmail(tmp_path, "20260211T130000Z")
        _create_gemmail(tmp_path, "20260211T140000Z")
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()
        # Tag one as Trash
        mbox.add_tag("20260211T140000Z", "Trash")
        return mbox

    def test_list_all_excludes_trash(self, tmp_path):
        mbox = self._make_mbox_with_tags(tmp_path)
        ids = mbox.list_all_msgids()
        assert "20260211T140000Z" not in ids
        assert len(ids) == 2

    def test_list_by_tag(self, tmp_path):
        mbox = self._make_mbox_with_tags(tmp_path)
        ids = mbox.list_by_tag("Inbox")
        # Trash message has Inbox tag but should be excluded
        assert "20260211T140000Z" not in ids
        assert len(ids) == 2

    def test_list_trash_tag(self, tmp_path):
        mbox = self._make_mbox_with_tags(tmp_path)
        ids = mbox.list_by_tag("Trash")
        assert ids == ["20260211T140000Z"]

    def test_list_by_tag_since(self, tmp_path):
        mbox = self._make_mbox_with_tags(tmp_path)
        since = datetime(2026, 2, 11, 12, 30, 0, tzinfo=UTC)
        ids = mbox.list_by_tag("Inbox", since=since)
        assert "20260211T120000Z" not in ids
        assert "20260211T130000Z" in ids


class TestGmapMailboxDelete:
    def test_delete_trash_message(self, tmp_path):
        path = _create_gemmail(tmp_path, "20260211T120000Z")
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()
        mbox.add_tag("20260211T120000Z", "Trash")

        assert mbox.delete_message("20260211T120000Z")
        assert not path.exists()
        assert "20260211T120000Z" not in mbox.messages

    def test_delete_non_trash_fails(self, tmp_path):
        _create_gemmail(tmp_path, "20260211T120000Z")
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        assert not mbox.delete_message("20260211T120000Z")

    def test_delete_nonexistent_fails(self, tmp_path):
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        assert not mbox.delete_message("nonexistent")


class TestGmapMailboxMessages:
    def test_get_message_bytes(self, tmp_path):
        content = (
            "sender@example.com\n"
            "recipient@example.com\n"
            "2026-02-11T12:00:00Z\n"
            "# Test\nBody\n"
        )
        _create_gemmail(tmp_path, "20260211T120000Z", content)
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        mbox.sync_filesystem()

        data = mbox.get_message_bytes("20260211T120000Z")
        assert data == content.encode("utf-8")

    def test_get_nonexistent_message(self, tmp_path):
        mbox = GmapMailbox(tmp_path)
        mbox.load()
        assert mbox.get_message_bytes("nonexistent") is None
