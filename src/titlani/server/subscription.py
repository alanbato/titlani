"""SQLite-backed pending subscription token store."""

import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tlacacoca import get_logger

logger = get_logger(__name__)

_DEFAULT_TTL = 86400  # 24 hours


class SubscriptionTokenStore:
    """Manages pending subscription tokens for mailing list verification.

    Stores tokens in SQLite with the same patterns as
    ``verification.cache.SenderVerificationCache``.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> None:
        if db_path is None:
            self._db_path = ":memory:"
        else:
            self._db_path = str(db_path)
        self._ttl_seconds = ttl_seconds
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        if self._db_path != ":memory:":
            os.chmod(self._db_path, 0o600)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_subscriptions (
                list_name TEXT NOT NULL,
                address TEXT NOT NULL,
                token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (list_name, address)
            )
            """
        )
        self._conn.commit()

    def __enter__(self) -> "SubscriptionTokenStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def create_token(self, list_name: str, address: str) -> str:
        """Create (or replace) a pending subscription token.

        Returns the 6-character hex token.
        """
        token = secrets.token_hex(3).upper()
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO pending_subscriptions
                (list_name, address, token, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(list_name, address) DO UPDATE SET
                token = excluded.token,
                created_at = excluded.created_at
            """,
            (list_name, address.lower(), token, now),
        )
        self._conn.commit()
        logger.debug(
            "subscription_token_created",
            list_name=list_name,
            address=address.lower(),
        )
        return token

    def verify_token(self, list_name: str, token: str) -> str | None:
        """Verify a token and consume it.

        Returns the address if valid and not expired, otherwise None.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur = self._conn.execute(
            "SELECT address FROM pending_subscriptions "
            "WHERE list_name = ? AND token = ? AND created_at >= ?",
            (list_name, token.upper(), cutoff.isoformat()),
        )
        row = cur.fetchone()
        if row is None:
            logger.debug(
                "subscription_token_invalid",
                list_name=list_name,
            )
            return None
        address = row[0]
        self._conn.execute(
            "DELETE FROM pending_subscriptions WHERE list_name = ? AND address = ?",
            (list_name, address),
        )
        self._conn.commit()
        logger.debug(
            "subscription_token_consumed",
            list_name=list_name,
            address=address,
        )
        return address

    def is_pending(self, list_name: str, address: str) -> bool:
        """Check if an address has a pending (non-expired) subscription."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur = self._conn.execute(
            "SELECT 1 FROM pending_subscriptions "
            "WHERE list_name = ? AND address = ? AND created_at >= ?",
            (list_name, address.lower(), cutoff.isoformat()),
        )
        return cur.fetchone() is not None

    def list_pending(self, list_name: str) -> list[tuple[str, str, datetime]]:
        """Return all pending entries as (address, token, created_at)."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur = self._conn.execute(
            "SELECT address, token, created_at "
            "FROM pending_subscriptions "
            "WHERE list_name = ? AND created_at >= ? "
            "ORDER BY created_at DESC",
            (list_name, cutoff.isoformat()),
        )
        results: list[tuple[str, str, datetime]] = []
        for address, token, ts_str in cur.fetchall():
            results.append((address, token, datetime.fromisoformat(ts_str)))
        return results

    def remove_pending(self, list_name: str, address: str) -> bool:
        """Remove a pending entry. Returns True if it existed."""
        cur = self._conn.execute(
            "DELETE FROM pending_subscriptions WHERE list_name = ? AND address = ?",
            (list_name, address.lower()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def cleanup(self) -> int:
        """Purge expired rows. Returns count of removed entries."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur = self._conn.execute(
            "DELETE FROM pending_subscriptions WHERE created_at < ?",
            (cutoff.isoformat(),),
        )
        self._conn.commit()
        count = cur.rowcount
        if count > 0:
            logger.info(
                "subscription_cleanup",
                expired_count=count,
            )
        return count

    def close(self) -> None:
        self._conn.close()
