"""Tests for GMAP handler routing and authentication."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from titlani.gmap.handler import (
    BAD_REQUEST,
    CERT_NOT_AUTHORIZED,
    CERT_REQUIRED,
    NOT_FOUND,
    SUCCESS,
    TEMP_FAILURE,
    GeminiRequest,
    GmapHandler,
    parse_gemini_request,
)
from titlani.identity.certificate import (
    MisfinIdentity,
    generate_identity_cert,
    normalize_fingerprint,
)


def _make_handler(tmp_path: Path) -> GmapHandler:
    return GmapHandler(mailbox_dir=tmp_path, hostname="example.com")


def _mock_cert(mailbox: str = "alice", hostname: str = "example.com"):
    cert = MagicMock()
    return cert


class TestParseGeminiRequest:
    def test_simple_url(self):
        req = parse_gemini_request(b"gemini://example.com/tag/Inbox")
        assert req.hostname == "example.com"
        assert req.path == "/tag/Inbox"
        assert req.query is None

    def test_url_with_query(self):
        req = parse_gemini_request(b"gemini://example.com/tag/Inbox?20260211T120000Z")
        assert req.path == "/tag/Inbox"
        assert req.query == "20260211T120000Z"

    def test_url_with_port(self):
        req = parse_gemini_request(b"gemini://example.com:1958/msgid/abc")
        assert req.hostname == "example.com"
        assert req.path == "/msgid/abc"

    def test_root_path(self):
        req = parse_gemini_request(b"gemini://example.com")
        assert req.path == "/"

    def test_not_gemini(self):
        with pytest.raises(ValueError, match="Not a Gemini URL"):
            parse_gemini_request(b"misfin://alice@example.com")

    def test_invalid_utf8(self):
        with pytest.raises(ValueError, match="Invalid UTF-8"):
            parse_gemini_request(b"gemini://example.com/\xff")


class TestGmapHandlerAuth:
    async def test_no_cert(self, tmp_path):
        handler = _make_handler(tmp_path)
        req = GeminiRequest(
            url="gemini://example.com/tag/",
            hostname="example.com",
            path="/tag/",
            query=None,
            client_cert=None,
        )
        resp = await handler.handle_request(req)
        assert resp.status == CERT_REQUIRED

    async def test_cert_missing_identity(self, tmp_path, make_gmap_request):
        handler = _make_handler(tmp_path)
        req = make_gmap_request("/tag/")

        with patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="", hostname=""),
        ):
            resp = await handler.handle_request(req)
        assert resp.status == CERT_NOT_AUTHORIZED

    async def test_mailbox_not_found(self, tmp_path, make_gmap_request):
        handler = _make_handler(tmp_path)
        req = make_gmap_request("/tag/")

        with patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="alice", hostname="example.com"),
        ):
            resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND


class TestGmapHandlerRoutes:
    """Test routes with a properly set up mailbox."""

    @pytest.fixture
    def setup(self, tmp_path, create_gemmail):
        mailbox_path = tmp_path / "alice"
        mailbox_path.mkdir()
        create_gemmail(mailbox_path, "20260211T120000Z")
        create_gemmail(mailbox_path, "20260211T130000Z")
        handler = _make_handler(tmp_path)
        return handler, mailbox_path

    def _patch_identity(self):
        return patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="alice", hostname="example.com"),
        )

    async def test_msgid_success(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/msgid/20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        assert resp.meta == "text/plain"
        assert b"sender@example.com" in resp.body

    async def test_msgid_not_found(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/msgid/nonexistent")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND

    async def test_tag_list_all(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/tag/")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        body = resp.body.decode()
        assert "20260211T120000Z" in body
        assert "20260211T130000Z" in body

    async def test_tag_list_inbox(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/tag/Inbox")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        body = resp.body.decode()
        assert "20260211T120000Z" in body
        assert "20260211T130000Z" in body

    async def test_add_tag(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/tag/Archive", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_add_invalid_tag(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/tag/bad tag!", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == BAD_REQUEST

    async def test_remove_tag(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/untag/Unread", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_remove_tag_missing_query(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/untag/Unread")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == BAD_REQUEST

    async def test_delete_requires_trash_tag(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/delete", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        # Message not in Trash, should fail
        assert resp.status == NOT_FOUND
        assert "Trash" in resp.meta

    async def test_delete_trash_message(self, setup, make_gmap_request):
        handler, mailbox_path = setup
        # First tag as Trash
        req = make_gmap_request("/tag/Trash", query="20260211T120000Z")
        with self._patch_identity():
            await handler.handle_request(req)

        # Now delete
        req = make_gmap_request("/delete", query="20260211T120000Z")
        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        assert not (mailbox_path / "20260211T120000Z.gemmail").exists()

    async def test_delete_missing_query(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/delete")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == BAD_REQUEST

    async def test_unknown_route(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/unknown/path")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND

    async def test_encrypted_message(self, setup, make_gmap_request):
        handler, mailbox_path = setup
        # Create an encrypted file
        (mailbox_path / "20260211T140000Z.gemmail.enc").write_bytes(b"encrypted")

        req = make_gmap_request("/msgid/20260211T140000Z")
        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == TEMP_FAILURE
        assert "encrypted" in resp.meta.lower()

    async def test_tag_list_with_timestamp(self, setup, make_gmap_request):
        handler, _ = setup
        req = make_gmap_request("/tag/Inbox/2026-02-11T12:30:00Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        body = resp.body.decode()
        # Only the message after 12:30 should appear
        assert "20260211T120000Z" not in body
        assert "20260211T130000Z" in body


class TestGmapListRoutes:
    """Test /list/ discovery and info routes."""

    @pytest.fixture
    def setup_lists(self, tmp_path, create_gemmail):
        """Create mailbox_dir with two lists and one regular mailbox."""
        # Mailing list: dev-announce
        dev = tmp_path / "dev-announce"
        dev.mkdir()
        (dev / "subscribers.txt").write_text(
            "# Development announcements\nalice@example.com\nbob@example.com\n"
        )
        create_gemmail(dev, "20260211T120000Z")
        create_gemmail(dev, "20260211T130000Z")

        # Mailing list: general
        gen = tmp_path / "general"
        gen.mkdir()
        (gen / "subscribers.txt").write_text("carol@example.com\n")
        create_gemmail(gen, "20260211T140000Z")

        # Regular mailbox (no subscribers.txt)
        personal = tmp_path / "alice"
        personal.mkdir()
        create_gemmail(personal, "20260211T150000Z")

        handler = GmapHandler(mailbox_dir=tmp_path, hostname="example.com")
        return handler

    async def test_list_discovery(self, setup_lists, make_gmap_request):
        handler = setup_lists
        req = make_gmap_request("/list/")
        resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        assert resp.meta == "text/gemini"
        body = resp.body.decode()
        assert "dev-announce" in body
        assert "general" in body
        assert "alice" not in body

    async def test_list_discovery_no_cert(self, setup_lists):
        handler = setup_lists
        req = GeminiRequest(
            url="gemini://example.com/list/",
            hostname="example.com",
            path="/list/",
            query=None,
            client_cert=None,
        )
        resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_list_info(self, setup_lists, make_gmap_request):
        handler = setup_lists
        req = make_gmap_request("/list/dev-announce/info")
        resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        assert resp.meta == "text/gemini"
        body = resp.body.decode()
        assert "# dev-announce" in body
        assert "Development announcements" in body
        assert "Subscribers: 2" in body
        assert "Messages: 2" in body
        assert "=> misfin:dev-announce@example.com?subscribe" in body
        assert "=> misfin:dev-announce@example.com?unsubscribe" in body

    async def test_list_info_not_found(self, setup_lists, make_gmap_request):
        handler = setup_lists
        req = make_gmap_request("/list/nonexistent/info")
        resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND

    async def test_list_unknown_route(self, setup_lists, make_gmap_request):
        handler = setup_lists
        req = make_gmap_request("/list/dev-announce/unknown")
        resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND


class TestGmapFingerprintVerification:
    """Test fingerprint-based authentication for GMAP."""

    @pytest.fixture
    def setup_with_cert(self, tmp_path, create_gemmail):
        """Create a mailbox and real identity cert for fingerprint tests."""
        from cryptography.x509 import load_pem_x509_certificate
        from tlacacoca import get_certificate_fingerprint

        mailbox_path = tmp_path / "alice"
        mailbox_path.mkdir()
        create_gemmail(mailbox_path, "20260211T120000Z")

        # Generate a real identity cert
        cert_pem, _ = generate_identity_cert(
            mailbox="alice",
            hostname="example.com",
        )
        cert = load_pem_x509_certificate(cert_pem)
        fp = normalize_fingerprint(get_certificate_fingerprint(cert))

        return tmp_path, cert, fp

    def _patch_identity(self):
        return patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="alice", hostname="example.com"),
        )

    async def test_fingerprint_match_allows_access(
        self, setup_with_cert, make_gmap_request
    ):
        tmp_path, cert, fp = setup_with_cert
        handler = GmapHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            recipient_fps={"alice": fp},
        )
        req = make_gmap_request("/tag/", client_cert=cert)

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_fingerprint_mismatch_rejected(
        self, setup_with_cert, make_gmap_request
    ):
        tmp_path, cert, _ = setup_with_cert
        handler = GmapHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            recipient_fps={"alice": "wrong" + "ff" * 31},
        )
        req = make_gmap_request("/tag/", client_cert=cert)

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == CERT_NOT_AUTHORIZED
        assert "mismatch" in resp.meta.lower()

    async def test_missing_registered_fingerprint_rejected(
        self, setup_with_cert, make_gmap_request
    ):
        tmp_path, cert, _ = setup_with_cert
        # Fingerprints exist for other mailboxes but not alice
        handler = GmapHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            recipient_fps={"bob": "aa" * 32},
        )
        req = make_gmap_request("/tag/", client_cert=cert)

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == CERT_NOT_AUTHORIZED
        assert "registered" in resp.meta.lower()

    async def test_empty_recipient_fps_skips_verification(
        self, setup_with_cert, make_gmap_request
    ):
        tmp_path, cert, _ = setup_with_cert
        # Empty dict = no fingerprint verification (backward compat)
        handler = GmapHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            recipient_fps={},
        )
        req = make_gmap_request("/tag/", client_cert=cert)

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_none_recipient_fps_skips_verification(
        self, setup_with_cert, make_gmap_request
    ):
        tmp_path, cert, _ = setup_with_cert
        handler = GmapHandler(
            mailbox_dir=tmp_path,
            hostname="example.com",
            recipient_fps=None,
        )
        req = make_gmap_request("/tag/", client_cert=cert)

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
