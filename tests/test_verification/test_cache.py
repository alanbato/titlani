"""Tests for SenderVerificationCache."""

import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from titlani.verification.cache import SenderVerificationCache


class TestSenderVerificationCache:
    def test_get_missing_returns_none(self) -> None:
        cache = SenderVerificationCache()
        assert cache.get_fingerprint("alice@example.com") is None
        cache.close()

    def test_add_and_get(self) -> None:
        cache = SenderVerificationCache()
        cache.add_verified("alice@example.com", "abc123")
        assert cache.get_fingerprint("alice@example.com") == "abc123"
        cache.close()

    def test_update_existing(self) -> None:
        cache = SenderVerificationCache()
        cache.add_verified("alice@example.com", "old")
        cache.add_verified("alice@example.com", "new")
        assert cache.get_fingerprint("alice@example.com") == "new"
        cache.close()

    def test_revoke(self) -> None:
        cache = SenderVerificationCache()
        cache.add_verified("alice@example.com", "abc123")
        assert cache.revoke("alice@example.com") is True
        assert cache.get_fingerprint("alice@example.com") is None
        assert cache.revoke("alice@example.com") is False
        cache.close()

    def test_list_verified(self) -> None:
        cache = SenderVerificationCache()
        cache.add_verified("alice@a.com", "aaa")
        cache.add_verified("bob@b.com", "bbb")
        entries = cache.list_verified()
        addresses = {addr for addr, _, _ in entries}
        assert addresses == {"alice@a.com", "bob@b.com"}
        cache.close()

    def test_persistent_storage(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"

        cache1 = SenderVerificationCache(db_path)
        cache1.add_verified("alice@example.com", "abc123")
        cache1.close()

        cache2 = SenderVerificationCache(db_path)
        assert cache2.get_fingerprint("alice@example.com") == "abc123"
        cache2.close()

    def test_db_file_has_600_permissions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "secure.db"
        cache = SenderVerificationCache(db_path)
        mode = stat.S_IMODE(db_path.stat().st_mode)
        assert mode == 0o600
        cache.close()

    def test_context_manager(self) -> None:
        with SenderVerificationCache() as cache:
            cache.add_verified("alice@example.com", "abc123")
            assert cache.get_fingerprint("alice@example.com") == "abc123"


class TestCacheTTL:
    def test_expired_entry_returns_none(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=60)
        cache.add_verified("alice@example.com", "abc123")

        # Simulate time passing beyond TTL
        future = datetime.now(UTC) + timedelta(seconds=120)
        with patch("titlani.verification.cache.datetime") as mock_dt:
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = cache.get_fingerprint("alice@example.com")

        assert result is None
        cache.close()

    def test_fresh_entry_returns_fingerprint(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=3600)
        cache.add_verified("alice@example.com", "abc123")
        assert cache.get_fingerprint("alice@example.com") == "abc123"
        cache.close()

    def test_cleanup_removes_expired(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=60)
        cache.add_verified("alice@example.com", "abc123")

        future = datetime.now(UTC) + timedelta(seconds=120)
        with patch("titlani.verification.cache.datetime") as mock_dt:
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            removed = cache.cleanup()

        assert removed == 1
        cache.close()

    def test_cleanup_keeps_fresh(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=3600)
        cache.add_verified("alice@example.com", "abc123")
        removed = cache.cleanup()
        assert removed == 0
        assert cache.get_fingerprint("alice@example.com") == "abc123"
        cache.close()


class TestServerSPKICache:
    def test_get_missing_returns_none(self) -> None:
        cache = SenderVerificationCache()
        assert cache.get_server_spki("example.com") is None
        cache.close()

    def test_add_and_get(self) -> None:
        cache = SenderVerificationCache()
        cache.add_server_spki("example.com", "abcdef1234567890")
        assert cache.get_server_spki("example.com") == "abcdef1234567890"
        cache.close()

    def test_update_existing(self) -> None:
        cache = SenderVerificationCache()
        cache.add_server_spki("example.com", "old_hash")
        cache.add_server_spki("example.com", "new_hash")
        assert cache.get_server_spki("example.com") == "new_hash"
        cache.close()

    def test_list_server_spki(self) -> None:
        cache = SenderVerificationCache()
        cache.add_server_spki("a.com", "hash_a")
        cache.add_server_spki("b.com", "hash_b")
        entries = cache.list_server_spki()
        hostnames = {h for h, _, _ in entries}
        assert hostnames == {"a.com", "b.com"}
        cache.close()

    def test_clear_server_spki(self) -> None:
        cache = SenderVerificationCache()
        cache.add_server_spki("a.com", "hash_a")
        cache.add_server_spki("b.com", "hash_b")
        count = cache.clear_server_spki()
        assert count == 2
        assert cache.get_server_spki("a.com") is None
        assert cache.get_server_spki("b.com") is None
        cache.close()

    def test_clear_empty_returns_zero(self) -> None:
        cache = SenderVerificationCache()
        assert cache.clear_server_spki() == 0
        cache.close()

    def test_expired_spki_returns_none(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=60)
        cache.add_server_spki("example.com", "hash123")

        future = datetime.now(UTC) + timedelta(seconds=120)
        with patch("titlani.verification.cache.datetime") as mock_dt:
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = cache.get_server_spki("example.com")

        assert result is None
        cache.close()

    def test_cleanup_removes_expired_spki(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=60)
        cache.add_server_spki("example.com", "hash123")

        future = datetime.now(UTC) + timedelta(seconds=120)
        with patch("titlani.verification.cache.datetime") as mock_dt:
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            removed = cache.cleanup()

        assert removed == 1
        cache.close()

    def test_get_last_spki_ignores_ttl(self) -> None:
        cache = SenderVerificationCache(ttl_seconds=60)
        cache.add_server_spki("example.com", "hash123")

        future = datetime.now(UTC) + timedelta(seconds=120)
        with patch("titlani.verification.cache.datetime") as mock_dt:
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # TTL-aware returns None
            assert cache.get_server_spki("example.com") is None
            # TTL-ignored returns the value
            assert cache.get_last_server_spki("example.com") == "hash123"
        cache.close()

    def test_spki_and_probe_tables_independent(self) -> None:
        cache = SenderVerificationCache()
        cache.add_verified("alice@example.com", "probe_fp")
        cache.add_server_spki("example.com", "spki_hash")
        assert cache.get_fingerprint("alice@example.com") == "probe_fp"
        assert cache.get_server_spki("example.com") == "spki_hash"
        cache.clear_server_spki()
        assert cache.get_fingerprint("alice@example.com") == "probe_fp"
        cache.close()
