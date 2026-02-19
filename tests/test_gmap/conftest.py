"""Shared fixtures for GMAP tests."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from titlani.gmap.handler import GeminiRequest


@pytest.fixture
def make_gmap_request() -> Callable[..., GeminiRequest]:
    """Factory for GeminiRequest with a mock client cert by default."""

    def _make(
        path: str,
        query: str | None = None,
        mailbox: str = "alice",
        hostname: str = "example.com",
        client_cert=None,
    ) -> GeminiRequest:
        if client_cert is None:
            client_cert = MagicMock()
        return GeminiRequest(
            url=f"gemini://example.com{path}",
            hostname="example.com",
            path=path,
            query=query,
            client_cert=client_cert,
        )

    return _make


@pytest.fixture
def create_gemmail() -> Callable[..., Path]:
    """Factory for writing .gemmail files to a mailbox directory."""

    def _make(
        mailbox_path: Path,
        msgid: str,
        content: str = "",
    ) -> Path:
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

    return _make
