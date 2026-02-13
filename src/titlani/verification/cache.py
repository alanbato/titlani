"""Persistent cache for verified sender fingerprints and server SPKI hashes."""

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

_DEFAULT_TTL = 604800  # 7 days


class SenderVerificationCache:
    """SQLite-backed cache for probe fingerprints and server SPKI hashes.

    Tables:
    - ``verified_senders``: maps sender addresses to probe fingerprints
    - ``server_spki``: maps hostnames to SPKI hashes (for SPKI verification)
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
            CREATE TABLE IF NOT EXISTS verified_senders (
                address TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                verified_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS server_spki (
                hostname TEXT PRIMARY KEY,
                spki_hash TEXT NOT NULL,
                verified_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def __enter__(self) -> "SenderVerificationCache":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_fingerprint(self, address: str) -> str | None:
        """Return cached fingerprint for *address*, or None if missing/expired."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur = self._conn.execute(
            "SELECT fingerprint FROM verified_senders "
            "WHERE address = ? AND verified_at >= ?",
            (address, cutoff.isoformat()),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def add_verified(self, address: str, fingerprint: str) -> None:
        """Store (or update) a verified sender."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO verified_senders (address, fingerprint, verified_at)
            VALUES (?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                fingerprint = excluded.fingerprint,
                verified_at = excluded.verified_at
            """,
            (address, fingerprint, now),
        )
        self._conn.commit()

    def revoke(self, address: str) -> bool:
        """Remove *address* from cache. Returns True if it existed."""
        cur = self._conn.execute(
            "DELETE FROM verified_senders WHERE address = ?",
            (address,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_verified(
        self,
    ) -> list[tuple[str, str, datetime]]:
        """Return all verified senders as (address, fingerprint, verified_at)."""
        cur = self._conn.execute(
            "SELECT address, fingerprint, verified_at "
            "FROM verified_senders ORDER BY verified_at DESC"
        )
        results: list[tuple[str, str, datetime]] = []
        for address, fingerprint, ts_str in cur.fetchall():
            results.append((address, fingerprint, datetime.fromisoformat(ts_str)))
        return results

    def cleanup(self) -> int:
        """Remove expired entries from all tables. Returns total purged rows."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur1 = self._conn.execute(
            "DELETE FROM verified_senders WHERE verified_at < ?",
            (cutoff.isoformat(),),
        )
        cur2 = self._conn.execute(
            "DELETE FROM server_spki WHERE verified_at < ?",
            (cutoff.isoformat(),),
        )
        self._conn.commit()
        return cur1.rowcount + cur2.rowcount

    # --- SPKI cache methods ---

    def get_server_spki(self, hostname: str) -> str | None:
        """Return cached SPKI hash for *hostname*, or None if missing/expired."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)
        cur = self._conn.execute(
            "SELECT spki_hash FROM server_spki WHERE hostname = ? AND verified_at >= ?",
            (hostname, cutoff.isoformat()),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def get_last_server_spki(self, hostname: str) -> str | None:
        """Return last known SPKI hash for *hostname*, ignoring TTL.

        Used during re-verification after cache expiry to detect key changes.
        """
        cur = self._conn.execute(
            "SELECT spki_hash FROM server_spki WHERE hostname = ?",
            (hostname,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def add_server_spki(self, hostname: str, spki_hash: str) -> None:
        """Store (or update) a server SPKI hash."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO server_spki (hostname, spki_hash, verified_at)
            VALUES (?, ?, ?)
            ON CONFLICT(hostname) DO UPDATE SET
                spki_hash = excluded.spki_hash,
                verified_at = excluded.verified_at
            """,
            (hostname, spki_hash, now),
        )
        self._conn.commit()

    def list_server_spki(self) -> list[tuple[str, str, datetime]]:
        """Return all server SPKI entries as (hostname, spki_hash, verified_at)."""
        cur = self._conn.execute(
            "SELECT hostname, spki_hash, verified_at "
            "FROM server_spki ORDER BY verified_at DESC"
        )
        results: list[tuple[str, str, datetime]] = []
        for hostname, spki_hash, ts_str in cur.fetchall():
            results.append((hostname, spki_hash, datetime.fromisoformat(ts_str)))
        return results

    def clear_server_spki(self) -> int:
        """Remove all server SPKI entries. Returns count of removed rows."""
        cur = self._conn.execute("DELETE FROM server_spki")
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
