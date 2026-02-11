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
from titlani.identity.certificate import MisfinIdentity


def _create_gemmail(mailbox_path: Path, msgid: str, content: str = "") -> Path:
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


def _make_handler(tmp_path: Path) -> GmapHandler:
    return GmapHandler(mailbox_dir=tmp_path, hostname="example.com")


def _mock_cert(mailbox: str = "alice", hostname: str = "example.com"):
    cert = MagicMock()
    return cert


def _make_request(
    path: str,
    query: str | None = None,
    mailbox: str = "alice",
    hostname: str = "example.com",
    client_cert=None,
) -> GeminiRequest:
    if client_cert is None:
        client_cert = _mock_cert(mailbox, hostname)
    return GeminiRequest(
        url=f"gemini://example.com{path}",
        hostname="example.com",
        path=path,
        query=query,
        client_cert=client_cert,
    )


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

    async def test_cert_missing_identity(self, tmp_path):
        handler = _make_handler(tmp_path)
        req = _make_request("/tag/")

        with patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="", hostname=""),
        ):
            resp = await handler.handle_request(req)
        assert resp.status == CERT_NOT_AUTHORIZED

    async def test_mailbox_not_found(self, tmp_path):
        handler = _make_handler(tmp_path)
        req = _make_request("/tag/")

        with patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="alice", hostname="example.com"),
        ):
            resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND


class TestGmapHandlerRoutes:
    """Test routes with a properly set up mailbox."""

    @pytest.fixture
    def setup(self, tmp_path):
        mailbox_path = tmp_path / "alice"
        mailbox_path.mkdir()
        _create_gemmail(mailbox_path, "20260211T120000Z")
        _create_gemmail(mailbox_path, "20260211T130000Z")
        handler = _make_handler(tmp_path)
        return handler, mailbox_path

    def _patch_identity(self):
        return patch(
            "titlani.gmap.handler.extract_identity",
            return_value=MisfinIdentity(mailbox="alice", hostname="example.com"),
        )

    async def test_msgid_success(self, setup):
        handler, _ = setup
        req = _make_request("/msgid/20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        assert resp.meta == "text/plain"
        assert b"sender@example.com" in resp.body

    async def test_msgid_not_found(self, setup):
        handler, _ = setup
        req = _make_request("/msgid/nonexistent")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND

    async def test_tag_list_all(self, setup):
        handler, _ = setup
        req = _make_request("/tag/")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        body = resp.body.decode()
        assert "20260211T120000Z" in body
        assert "20260211T130000Z" in body

    async def test_tag_list_inbox(self, setup):
        handler, _ = setup
        req = _make_request("/tag/Inbox")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        body = resp.body.decode()
        assert "20260211T120000Z" in body
        assert "20260211T130000Z" in body

    async def test_add_tag(self, setup):
        handler, _ = setup
        req = _make_request("/tag/Archive", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_add_invalid_tag(self, setup):
        handler, _ = setup
        req = _make_request("/tag/bad tag!", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == BAD_REQUEST

    async def test_remove_tag(self, setup):
        handler, _ = setup
        req = _make_request("/untag/Unread", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS

    async def test_remove_tag_missing_query(self, setup):
        handler, _ = setup
        req = _make_request("/untag/Unread")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == BAD_REQUEST

    async def test_delete_requires_trash_tag(self, setup):
        handler, _ = setup
        req = _make_request("/delete", query="20260211T120000Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        # Message not in Trash, should fail
        assert resp.status == NOT_FOUND
        assert "Trash" in resp.meta

    async def test_delete_trash_message(self, setup):
        handler, mailbox_path = setup
        # First tag as Trash
        req = _make_request("/tag/Trash", query="20260211T120000Z")
        with self._patch_identity():
            await handler.handle_request(req)

        # Now delete
        req = _make_request("/delete", query="20260211T120000Z")
        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        assert not (mailbox_path / "20260211T120000Z.gemmail").exists()

    async def test_delete_missing_query(self, setup):
        handler, _ = setup
        req = _make_request("/delete")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == BAD_REQUEST

    async def test_unknown_route(self, setup):
        handler, _ = setup
        req = _make_request("/unknown/path")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == NOT_FOUND

    async def test_encrypted_message(self, setup):
        handler, mailbox_path = setup
        # Create an encrypted file
        (mailbox_path / "20260211T140000Z.gemmail.enc").write_bytes(b"encrypted")

        req = _make_request("/msgid/20260211T140000Z")
        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == TEMP_FAILURE
        assert "encrypted" in resp.meta.lower()

    async def test_tag_list_with_timestamp(self, setup):
        handler, _ = setup
        req = _make_request("/tag/Inbox/2026-02-11T12:30:00Z")

        with self._patch_identity():
            resp = await handler.handle_request(req)
        assert resp.status == SUCCESS
        body = resp.body.decode()
        # Only the message after 12:30 should appear
        assert "20260211T120000Z" not in body
        assert "20260211T130000Z" in body
