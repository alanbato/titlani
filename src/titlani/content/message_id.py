"""Message ID generation and threading utilities.

Message IDs are 8-character lowercase hex strings derived from
SHA-256(sender:timestamp). They are embedded in filenames:

    YYYYMMDDTHHMMSSZ-<8hex>.gemmail[.enc][.new]

Threading uses gemtext link lines in the message body:

    => mid:<message-id> In reply to
"""

import hashlib
import re
from datetime import datetime

# Matches new-format filenames: YYYYMMDDTHHMMSSZ-<hex>.gemmail[.enc][.new]
_NEW_FORMAT_RE = re.compile(r"^(\d{8}T\d{6}Z)-([0-9a-f]+)$")
# Matches old-format filenames: YYYYMMDDTHHMMSSZ.gemmail[.enc][.new]
_OLD_FORMAT_RE = re.compile(r"^(\d{8}T\d{6}Z)$")

_SUFFIXES = (".gemmail.enc.new", ".gemmail.enc", ".gemmail.new", ".gemmail")

# Matches => mid:<id> links in gemtext body
_REPLY_LINK_RE = re.compile(r"^=>\s*mid:(\S+)", re.MULTILINE)


def generate_message_id(sender: str, timestamp: datetime) -> str:
    """Generate an 8-character hex message ID.

    Uses SHA-256 of "sender:ISO-timestamp" truncated to 8 hex chars.
    Microseconds are included in the hash input so that messages
    arriving within the same second still get distinct IDs.
    """
    ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    data = f"{sender}:{ts_str}".encode()
    return hashlib.sha256(data).hexdigest()[:8]


def parse_message_id_from_filename(filename: str) -> str | None:
    """Extract message ID from a gemmail filename.

    Handles both formats:
        '20260211T143052Z-a1b2c3d4.gemmail' -> '20260211T143052Z-a1b2c3d4'
        '20260211T143052Z.gemmail'           -> '20260211T143052Z'

    Returns None for unrecognized filenames.
    """
    stem = filename
    for suffix in _SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        return None

    if _NEW_FORMAT_RE.fullmatch(stem):
        return stem
    if _OLD_FORMAT_RE.fullmatch(stem):
        return stem
    return None


def extract_reply_to_ids(body: str) -> list[str]:
    """Parse message IDs from ``=> mid:<id>`` gemtext links."""
    return _REPLY_LINK_RE.findall(body)


def build_reply_link(message_id: str) -> str:
    """Build a gemtext reply link line."""
    return f"=> mid:{message_id} In reply to"
