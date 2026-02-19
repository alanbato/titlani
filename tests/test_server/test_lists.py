"""Tests for mailing list utilities in server.lists."""

from titlani.content.gemmail import GemmailMessage, MisfinAddress
from titlani.server.lists import (
    get_list_description,
    get_or_create_list_identity,
    is_mailing_list,
    is_subscriber,
    load_subscribers,
    should_prevent_loop,
)


class TestIsMailingList:
    def test_true_when_subscribers_file_exists(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("alice@example.com\n")
        assert is_mailing_list(tmp_path) is True

    def test_false_when_no_subscribers_file(self, tmp_path):
        assert is_mailing_list(tmp_path) is False

    def test_true_for_empty_subscribers_file(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("")
        assert is_mailing_list(tmp_path) is True


class TestGetListDescription:
    def test_returns_first_comment(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text(
            "# Development announcements\nalice@example.com\n"
        )
        assert get_list_description(tmp_path) == "Development announcements"

    def test_returns_none_when_no_comments(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("alice@example.com\n")
        assert get_list_description(tmp_path) is None

    def test_returns_none_when_file_missing(self, tmp_path):
        assert get_list_description(tmp_path) is None

    def test_strips_multiple_hashes(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("## My List\n")
        assert get_list_description(tmp_path) == "My List"


class TestLoadSubscribers:
    def test_parses_valid_addresses(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("alice@example.com\nbob@other.com\n")
        subs = load_subscribers(tmp_path)
        assert subs == ["alice@example.com", "bob@other.com"]

    def test_ignores_blank_lines(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text(
            "alice@example.com\n\n\nbob@other.com\n"
        )
        subs = load_subscribers(tmp_path)
        assert subs == ["alice@example.com", "bob@other.com"]

    def test_ignores_comment_lines(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text(
            "# This is a comment\nalice@example.com\n# Another comment\n"
        )
        subs = load_subscribers(tmp_path)
        assert subs == ["alice@example.com"]

    def test_lowercases_addresses(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("Alice@Example.COM\n")
        subs = load_subscribers(tmp_path)
        assert subs == ["alice@example.com"]

    def test_skips_invalid_addresses(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text(
            "alice@example.com\nnot-an-address\nbob@other.com\n"
        )
        subs = load_subscribers(tmp_path)
        assert subs == ["alice@example.com", "bob@other.com"]

    def test_returns_empty_list_when_file_missing(self, tmp_path):
        assert load_subscribers(tmp_path) == []

    def test_returns_empty_for_empty_file(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("")
        assert load_subscribers(tmp_path) == []

    def test_returns_empty_for_comments_only(self, tmp_path):
        (tmp_path / "subscribers.txt").write_text("# just a comment\n")
        assert load_subscribers(tmp_path) == []


class TestIsSubscriber:
    def test_match(self):
        assert is_subscriber("alice@example.com", ["alice@example.com"]) is True

    def test_case_insensitive(self):
        assert is_subscriber("Alice@Example.COM", ["alice@example.com"]) is True

    def test_no_match(self):
        assert is_subscriber("eve@evil.com", ["alice@example.com"]) is False

    def test_empty_list(self):
        assert is_subscriber("alice@example.com", []) is False


class TestShouldPreventLoop:
    def _make_msg(self, recipients: list[str]) -> GemmailMessage:
        recips = []
        for addr in recipients:
            m, h = addr.split("@")
            recips.append(MisfinAddress(m, h))
        return GemmailMessage(
            senders=[MisfinAddress("sender", "example.com")],
            recipients=recips,
            body="test\n",
        )

    def test_loop_detected(self):
        msg = self._make_msg(["mylist@example.com", "alice@example.com"])
        assert should_prevent_loop(msg, "mylist@example.com") is True

    def test_no_loop(self):
        msg = self._make_msg(["alice@example.com"])
        assert should_prevent_loop(msg, "mylist@example.com") is False

    def test_case_insensitive(self):
        msg = self._make_msg(["MyList@Example.COM"])
        assert should_prevent_loop(msg, "mylist@example.com") is True

    def test_empty_recipients(self):
        msg = self._make_msg([])
        assert should_prevent_loop(msg, "mylist@example.com") is False


class TestGetOrCreateListIdentity:
    def test_generates_new_certs(self, tmp_path):
        cert, key = get_or_create_list_identity(tmp_path, "announcements", "example.com")
        assert cert.exists()
        assert key.exists()
        assert cert.name == ".list-identity.crt"
        assert key.name == ".list-identity.key"

    def test_reuses_existing_certs(self, tmp_path):
        cert1, key1 = get_or_create_list_identity(
            tmp_path, "announcements", "example.com"
        )
        cert1_bytes = cert1.read_bytes()

        cert2, key2 = get_or_create_list_identity(
            tmp_path, "announcements", "example.com"
        )
        assert cert2.read_bytes() == cert1_bytes

    def test_restrictive_permissions(self, tmp_path):
        cert, key = get_or_create_list_identity(tmp_path, "announcements", "example.com")
        import stat

        assert stat.S_IMODE(cert.stat().st_mode) == 0o600
        assert stat.S_IMODE(key.stat().st_mode) == 0o600

    def test_cert_contains_correct_identity(self, tmp_path):
        from cryptography.x509 import load_pem_x509_certificate

        from titlani.identity.certificate import extract_identity

        cert_path, _ = get_or_create_list_identity(
            tmp_path, "announcements", "example.com"
        )
        cert = load_pem_x509_certificate(cert_path.read_bytes())
        identity = extract_identity(cert)
        assert identity.mailbox == "announcements"
        assert identity.hostname == "example.com"
        assert "mailing list" in identity.blurb
