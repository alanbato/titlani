"""Shared fixtures for server tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from titlani.server.handler import FileMailboxHandler


@pytest.fixture
def file_mailbox_handler(mailbox_dir: Path) -> Callable[..., FileMailboxHandler]:
    """Factory for FileMailboxHandler bound to the shared mailbox_dir."""

    def _make(hostname: str = "example.com", **kwargs) -> FileMailboxHandler:
        return FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname=hostname,
            **kwargs,
        )

    return _make
