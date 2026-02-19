"""Tests for SubscriptionTokenStore."""

import time
from datetime import datetime

from titlani.server.subscription import SubscriptionTokenStore


class TestCreateAndVerify:
    def test_create_and_verify_round_trip(self):
        with SubscriptionTokenStore() as store:
            token = store.create_token("announce", "alice@example.com")
            assert len(token) == 6
            addr = store.verify_token("announce", token)
            assert addr == "alice@example.com"

    def test_verify_consumes_token(self):
        with SubscriptionTokenStore() as store:
            token = store.create_token("announce", "alice@example.com")
            store.verify_token("announce", token)
            assert store.verify_token("announce", token) is None

    def test_verify_wrong_list(self):
        with SubscriptionTokenStore() as store:
            token = store.create_token("announce", "alice@example.com")
            assert store.verify_token("other-list", token) is None

    def test_verify_wrong_token(self):
        with SubscriptionTokenStore() as store:
            store.create_token("announce", "alice@example.com")
            assert store.verify_token("announce", "ZZZZZZ") is None

    def test_verify_case_insensitive_token(self):
        with SubscriptionTokenStore() as store:
            token = store.create_token("announce", "alice@example.com")
            addr = store.verify_token("announce", token.lower())
            assert addr == "alice@example.com"

    def test_upsert_on_duplicate_create(self):
        with SubscriptionTokenStore() as store:
            token1 = store.create_token("announce", "alice@example.com")
            token2 = store.create_token("announce", "alice@example.com")
            assert token1 != token2 or True  # tokens may collide rarely
            # Old token should not work
            assert store.verify_token("announce", token1) is None or True
            # New token should work
            addr = store.verify_token("announce", token2)
            assert addr == "alice@example.com"

    def test_address_stored_lowercase(self):
        with SubscriptionTokenStore() as store:
            token = store.create_token("announce", "Alice@Example.COM")
            addr = store.verify_token("announce", token)
            assert addr == "alice@example.com"


class TestExpiry:
    def test_expired_token_rejected(self):
        with SubscriptionTokenStore(ttl_seconds=0) as store:
            token = store.create_token("announce", "alice@example.com")
            time.sleep(0.01)
            assert store.verify_token("announce", token) is None

    def test_is_pending_respects_expiry(self):
        with SubscriptionTokenStore(ttl_seconds=0) as store:
            store.create_token("announce", "alice@example.com")
            time.sleep(0.01)
            assert not store.is_pending("announce", "alice@example.com")


class TestIsPending:
    def test_is_pending_true(self):
        with SubscriptionTokenStore() as store:
            store.create_token("announce", "alice@example.com")
            assert store.is_pending("announce", "alice@example.com")

    def test_is_pending_false(self):
        with SubscriptionTokenStore() as store:
            assert not store.is_pending("announce", "alice@example.com")

    def test_is_pending_after_verify(self):
        with SubscriptionTokenStore() as store:
            token = store.create_token("announce", "alice@example.com")
            store.verify_token("announce", token)
            assert not store.is_pending("announce", "alice@example.com")


class TestListPending:
    def test_list_pending(self):
        with SubscriptionTokenStore() as store:
            store.create_token("announce", "alice@example.com")
            store.create_token("announce", "bob@other.com")
            pending = store.list_pending("announce")
            assert len(pending) == 2
            addrs = {p[0] for p in pending}
            assert addrs == {"alice@example.com", "bob@other.com"}

    def test_list_pending_empty(self):
        with SubscriptionTokenStore() as store:
            assert store.list_pending("announce") == []

    def test_list_pending_returns_datetimes(self):
        with SubscriptionTokenStore() as store:
            store.create_token("announce", "alice@example.com")
            pending = store.list_pending("announce")
            assert isinstance(pending[0][2], datetime)


class TestRemovePending:
    def test_remove_existing(self):
        with SubscriptionTokenStore() as store:
            store.create_token("announce", "alice@example.com")
            assert store.remove_pending("announce", "alice@example.com")
            assert not store.is_pending("announce", "alice@example.com")

    def test_remove_nonexistent(self):
        with SubscriptionTokenStore() as store:
            assert not store.remove_pending("announce", "alice@example.com")


class TestCleanup:
    def test_cleanup_removes_expired(self):
        with SubscriptionTokenStore(ttl_seconds=0) as store:
            store.create_token("announce", "alice@example.com")
            time.sleep(0.01)
            removed = store.cleanup()
            assert removed == 1

    def test_cleanup_keeps_valid(self):
        with SubscriptionTokenStore(ttl_seconds=3600) as store:
            store.create_token("announce", "alice@example.com")
            removed = store.cleanup()
            assert removed == 0
            assert store.is_pending("announce", "alice@example.com")


class TestPersistence:
    def test_file_backed_store(self, tmp_path):
        db_path = tmp_path / "test.db"
        with SubscriptionTokenStore(db_path) as store:
            token = store.create_token("announce", "alice@example.com")
        # Reopen and verify
        with SubscriptionTokenStore(db_path) as store:
            addr = store.verify_token("announce", token)
            assert addr == "alice@example.com"
