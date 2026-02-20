"""Per-mailbox GMAP index and message operations.

Manages a `.gmap.json` file that tracks message IDs, tags, and timestamps.
Syncs with the filesystem to discover new messages delivered by the Misfin
server and auto-tags them with Inbox and Unread.
"""

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tlacacoca import get_logger

from ..server.lists import is_mailing_list

logger = get_logger(__name__)

REQUIRED_TAGS = frozenset({"Inbox", "Archive", "Sent", "Drafts", "Trash", "Unread"})
TAG_PATTERN = re.compile(r"^[a-zA-Z0-9_:-]+$")
INDEX_VERSION = 1


@dataclass
class MessageEntry:
    tags: set[str] = field(default_factory=set)
    timestamp: str = ""
    filename: str = ""


class GmapMailbox:
    """Manages the GMAP index for a single mailbox directory."""

    def __init__(self, mailbox_path: Path) -> None:
        self.mailbox_path = mailbox_path
        self.index_path = mailbox_path / ".gmap.json"
        self.messages: dict[str, MessageEntry] = {}
        self._loaded = False
        self._is_list = is_mailing_list(mailbox_path)

    def load(self) -> None:
        """Load index from disk. Creates empty index if missing."""
        if not self.index_path.exists():
            self.messages = {}
            self._loaded = True
            return

        try:
            data = json.loads(self.index_path.read_text("utf-8"))
            msgs = data.get("messages", {})
            self.messages = {}
            for msgid, info in msgs.items():
                self.messages[msgid] = MessageEntry(
                    tags=set(info.get("tags", [])),
                    timestamp=info.get("timestamp", ""),
                    filename=info.get("filename", ""),
                )
            self._loaded = True
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning(
                "gmap_index_corrupt",
                path=str(self.index_path),
            )
            self.messages = {}
            self._loaded = True

    def save(self) -> None:
        """Write index to disk atomically (temp + rename)."""
        data = {
            "version": INDEX_VERSION,
            "messages": {
                msgid: {
                    "tags": sorted(entry.tags),
                    "timestamp": entry.timestamp,
                    "filename": entry.filename,
                }
                for msgid, entry in sorted(self.messages.items())
            },
        }
        content = json.dumps(data, indent=2) + "\n"
        fd, tmp_path = tempfile.mkstemp(dir=self.mailbox_path, suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = -1  # Mark as closed
            os.replace(tmp_path, self.index_path)
        except BaseException:
            logger.error(
                "gmap_index_save_failed",
                path=str(self.index_path),
            )
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def sync_filesystem(self) -> bool:
        """Scan mailbox for new .gemmail files not in the index.

        Auto-tags new messages with Inbox and Unread.
        Returns True if index was modified.
        """
        if not self._loaded:
            self.load()

        modified = False
        known_files = {e.filename for e in self.messages.values()}

        # Discover .gemmail and .gemmail.enc files (including .new unread)
        for pattern in (
            "*.gemmail",
            "*.gemmail.new",
            "*.gemmail.enc",
            "*.gemmail.enc.new",
        ):
            for path in self.mailbox_path.glob(pattern):
                if path.name.startswith("."):
                    continue
                if path.name in known_files:
                    continue

                msgid = _filename_to_msgid(path.name)
                if not msgid:
                    continue

                if msgid in self.messages:
                    # File was renamed (e.g. .new removed on read);
                    # update filename but preserve existing tags.
                    self.messages[msgid].filename = path.name
                    modified = True
                    continue

                ts = _parse_timestamp_from_msgid(msgid)
                tags = {"Inbox", "Unread"}
                if self._is_list:
                    tags.add("List")
                self.messages[msgid] = MessageEntry(
                    tags=tags,
                    timestamp=ts,
                    filename=path.name,
                )
                modified = True
                logger.debug(
                    "gmap_indexed_new_message",
                    msgid=msgid,
                    filename=path.name,
                )

        # Remove entries whose files no longer exist
        if self._remove_stale_entries():
            modified = True

        return modified

    def _remove_stale_entries(self) -> bool:
        """Remove index entries whose files no longer exist on disk."""
        to_remove = [
            msgid
            for msgid, entry in self.messages.items()
            if not (self.mailbox_path / entry.filename).exists()
        ]
        for msgid in to_remove:
            del self.messages[msgid]
            logger.debug("gmap_removed_missing", msgid=msgid)
        return bool(to_remove)

    def list_all_msgids(self) -> list[str]:
        """Return all message IDs (excluding Trash)."""
        return [
            msgid for msgid, entry in self.messages.items() if "Trash" not in entry.tags
        ]

    def list_by_tag(
        self,
        tag: str,
        since: datetime | None = None,
    ) -> list[str]:
        """Return message IDs with the given tag.

        Messages tagged Trash are excluded unless querying Trash itself.
        """
        result = []
        for msgid, entry in self.messages.items():
            if tag not in entry.tags:
                continue
            if tag != "Trash" and "Trash" in entry.tags:
                continue
            if since is not None:
                msg_time = _parse_iso_timestamp(entry.timestamp)
                if msg_time is not None and msg_time < since:
                    continue
            result.append(msgid)
        return result

    def get_message_bytes(self, msgid: str) -> bytes | None:
        """Read a message file and return its raw bytes."""
        entry = self.messages.get(msgid)
        if entry is None:
            return None
        filepath = self.mailbox_path / entry.filename
        if not filepath.exists():
            return None
        return filepath.read_bytes()

    def is_encrypted(self, msgid: str) -> bool:
        """Check if a message is encrypted (.gemmail.enc or .gemmail.enc.new)."""
        entry = self.messages.get(msgid)
        if entry is None:
            return False
        return ".enc" in entry.filename

    def add_tag(self, msgid: str, tag: str) -> bool:
        """Add a tag to a message. Returns True if changed."""
        if not _valid_tag(tag):
            return False
        entry = self.messages.get(msgid)
        if entry is None:
            return False
        if tag in entry.tags:
            return True  # Already tagged, spec says update timestamp
        entry.tags.add(tag)
        return True

    def remove_tag(self, msgid: str, tag: str) -> bool:
        """Remove a tag from a message. Returns True if changed."""
        entry = self.messages.get(msgid)
        if entry is None:
            return False
        if tag not in entry.tags:
            return True  # Already untagged
        entry.tags.discard(tag)
        return True

    def delete_message(self, msgid: str) -> bool:
        """Permanently delete a message. Only succeeds if tagged Trash."""
        entry = self.messages.get(msgid)
        if entry is None:
            return False
        if "Trash" not in entry.tags:
            return False

        filepath = self.mailbox_path / entry.filename
        if filepath.exists():
            filepath.unlink()
            logger.info(
                "gmap_message_file_deleted",
                msgid=msgid,
                filename=entry.filename,
            )
        del self.messages[msgid]
        return True

    def has_message(self, msgid: str) -> bool:
        return msgid in self.messages


def _filename_to_msgid(filename: str) -> str | None:
    """Extract message ID from filename.

    New format (with hash):
    '20260211T143052Z-a1b2c3d4.gemmail' -> '20260211T143052Z-a1b2c3d4'

    Old format (timestamp only):
    '20260211T143052Z.gemmail' -> '20260211T143052Z'
    """
    from ..content.message_id import parse_message_id_from_filename

    return parse_message_id_from_filename(filename)


def _parse_timestamp_from_msgid(msgid: str) -> str:
    """Convert message ID to ISO 8601 timestamp.

    Handles both ``YYYYMMDDTHHMMSSZ`` and ``YYYYMMDDTHHMMSSZ-<hex>`` formats.
    """
    ts_part = msgid.split("-", 1)[0] if "-" in msgid else msgid
    try:
        dt = datetime.strptime(ts_part, "%Y%m%dT%H%M%SZ")
        return dt.replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ""


def _parse_iso_timestamp(ts: str) -> datetime | None:
    """Parse ISO 8601 timestamp to datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _valid_tag(tag: str) -> bool:
    """Validate a tag name: alphanumeric + underscore + hyphen."""
    return bool(TAG_PATTERN.match(tag))
