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

logger = get_logger(__name__)

REQUIRED_TAGS = frozenset({"Inbox", "Archive", "Sent", "Drafts", "Trash", "Unread"})
TAG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
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

        # Discover .gemmail and .gemmail.enc files
        for pattern in ("*.gemmail", "*.gemmail.enc"):
            for path in self.mailbox_path.glob(pattern):
                if path.name.startswith("."):
                    continue
                if path.name in known_files:
                    continue

                msgid = _filename_to_msgid(path.name)
                if not msgid:
                    continue

                ts = _parse_timestamp_from_msgid(msgid)
                self.messages[msgid] = MessageEntry(
                    tags={"Inbox", "Unread"},
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
        to_remove = []
        for msgid, entry in self.messages.items():
            if not (self.mailbox_path / entry.filename).exists():
                to_remove.append(msgid)
        for msgid in to_remove:
            del self.messages[msgid]
            modified = True
            logger.debug("gmap_removed_missing", msgid=msgid)

        return modified

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
        """Check if a message is encrypted (.gemmail.enc)."""
        entry = self.messages.get(msgid)
        if entry is None:
            return False
        return entry.filename.endswith(".enc")

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
        del self.messages[msgid]
        return True

    def has_message(self, msgid: str) -> bool:
        return msgid in self.messages


def _filename_to_msgid(filename: str) -> str | None:
    """Extract message ID from filename.

    '20260211T143052Z.gemmail' -> '20260211T143052Z'
    '20260211T143052Z.gemmail.enc' -> '20260211T143052Z'
    """
    stem = filename
    if stem.endswith(".gemmail.enc"):
        stem = stem[: -len(".gemmail.enc")]
    elif stem.endswith(".gemmail"):
        stem = stem[: -len(".gemmail")]
    else:
        return None

    # Validate format: YYYYMMDDTHHMMSSZ
    if re.fullmatch(r"\d{8}T\d{6}Z", stem):
        return stem
    return None


def _parse_timestamp_from_msgid(msgid: str) -> str:
    """Convert YYYYMMDDTHHMMSSZ to ISO 8601 timestamp."""
    try:
        dt = datetime.strptime(msgid, "%Y%m%dT%H%M%SZ")
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
