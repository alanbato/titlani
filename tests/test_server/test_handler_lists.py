"""Tests for mailing list integration in FileMailboxHandler."""

import asyncio
from unittest.mock import AsyncMock, patch

from titlani.protocol.request import MisfinRequest
from titlani.protocol.status import StatusCode
from titlani.server.handler import FileMailboxHandler
from titlani.server.lists import load_subscribers
from titlani.server.subscription import SubscriptionTokenStore


def _make_valid_message(
    sender: str = "alice@sender.example",
) -> bytes:
    return (f"{sender}\nbob@example.com\n2025-01-01T00:00:00Z\nHello!\n").encode()


def _make_request(
    mailbox: str,
    hostname: str = "example.com",
    message: bytes | None = None,
) -> MisfinRequest:
    if message is None:
        message = _make_valid_message()
    return MisfinRequest(
        mailbox=mailbox,
        hostname=hostname,
        content_length=len(message),
        raw_message=message,
    )


def _setup_list(tmp_path, listname="announce", subscribers=None):
    """Create a list mailbox with subscribers.txt."""
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir()
    list_path = mailbox_dir / listname
    list_path.mkdir()
    if subscribers is None:
        subscribers = ["alice@sender.example", "bob@other.com"]
    content = "\n".join(subscribers) + "\n"
    (list_path / "subscribers.txt").write_text(content)
    return mailbox_dir


class TestListPostingRestriction:
    async def test_subscriber_can_post(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )
        request = _make_request(
            "announce",
            message=_make_valid_message("alice@sender.example"),
        )
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    async def test_non_subscriber_rejected(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )
        request = _make_request(
            "announce",
            message=_make_valid_message("eve@evil.com"),
        )
        response = await handler.handle_message(request)
        assert response.status == StatusCode.UNAUTHORIZED_SENDER
        assert "subscribers" in response.meta.lower()

    async def test_non_subscriber_accepted_when_lists_disabled(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=False,
        )
        request = _make_request(
            "announce",
            message=_make_valid_message("eve@evil.com"),
        )
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

    async def test_regular_mailbox_unaffected_by_lists(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        (mailbox_dir / "alice").mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )
        request = _make_request("alice")
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS


class TestListForwardingTrigger:
    async def test_forwarding_triggered_for_list(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )
        with patch.object(
            handler, "_forward_to_list", new_callable=AsyncMock
        ) as mock_forward:
            request = _make_request(
                "announce",
                message=_make_valid_message("alice@sender.example"),
            )
            response = await handler.handle_message(request)
            assert response.status == StatusCode.SUCCESS
            # ensure_future was called, so _forward_to_list should be invoked
            # We need to await the scheduled task
            import asyncio

            await asyncio.sleep(0)
            assert mock_forward.called

    async def test_forwarding_not_triggered_when_disabled(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=False,
        )
        with patch.object(
            handler, "_forward_to_list", new_callable=AsyncMock
        ) as mock_forward:
            request = _make_request(
                "announce",
                message=_make_valid_message("alice@sender.example"),
            )
            await handler.handle_message(request)
            assert not mock_forward.called

    async def test_forwarding_not_triggered_for_regular_mailbox(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()
        (mailbox_dir / "alice").mkdir()

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )
        with patch.object(
            handler, "_forward_to_list", new_callable=AsyncMock
        ) as mock_forward:
            request = _make_request("alice")
            await handler.handle_message(request)
            import asyncio

            await asyncio.sleep(0)
            assert not mock_forward.called


class TestListForwarding:
    async def test_forwards_to_all_subscribers_except_sender(self, tmp_path):
        mailbox_dir = _setup_list(
            tmp_path,
            subscribers=[
                "alice@sender.example",
                "bob@other.com",
                "carol@third.com",
            ],
        )
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )

        mock_response = AsyncMock()
        mock_response.status = 20

        with patch("titlani.client.session.MisfinClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.send.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            from titlani.content.gemmail import (
                GemmailMessage,
                MisfinAddress,
            )

            msg = GemmailMessage(
                senders=[MisfinAddress("alice", "sender.example")],
                recipients=[MisfinAddress("announce", "example.com")],
                body="# Test\n\nHello list!\n",
            )

            await handler._forward_to_list(
                "announce",
                mailbox_dir / "announce",
                msg,
                ["alice@sender.example", "bob@other.com", "carol@third.com"],
            )

            # alice is the sender, so only bob and carol get forwards
            assert mock_client.send.call_count == 2
            recipients = {call.kwargs["to"] for call in mock_client.send.call_args_list}
            assert recipients == {"bob@other.com", "carol@third.com"}

    async def test_loop_prevention(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )

        # Message that already has the list address in recipients
        msg = _make_valid_message("alice@sender.example")
        msg_text = msg.decode()
        # Replace recipient line to include list address
        lines = msg_text.split("\n")
        lines[1] = "announce@example.com, bob@other.com"
        modified_msg = "\n".join(lines).encode()

        request = _make_request("announce", message=modified_msg)
        response = await handler.handle_message(request)
        # Loop is detected in _check_list_posting, returning BAD_REQUEST
        assert response.status == StatusCode.BAD_REQUEST
        assert "loop" in response.meta.lower()


class TestListArchiving:
    async def test_message_stored_when_archiving(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
            lists_archive=True,
        )
        request = _make_request(
            "announce",
            message=_make_valid_message("alice@sender.example"),
        )
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

        # Message should be stored in the list mailbox
        files = list((mailbox_dir / "announce").glob("*.gemmail.new"))
        assert len(files) == 1

    async def test_message_not_stored_when_archive_disabled(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path)
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
            lists_archive=False,
        )
        request = _make_request(
            "announce",
            message=_make_valid_message("alice@sender.example"),
        )
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

        # Message should NOT be stored
        files = list((mailbox_dir / "announce").glob("*.gemmail*"))
        assert len(files) == 0


def _make_command_message(
    sender: str,
    recipient: str,
    command: str,
) -> bytes:
    """Build a gemmail message whose body is a subscription command.

    The recipient in gemmail metadata is the sender's own address (not
    the list address) to avoid triggering loop detection. The actual
    list routing is determined by the request URL, not gemmail metadata.
    """
    return (f"{sender}\n{sender}\n2025-01-01T00:00:00Z\n{command}\n").encode()


class TestSubscriptionCommands:
    def _make_handler(self, mailbox_dir, store):
        return FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
            subscription_store=store,
        )

    async def test_subscribe_creates_pending(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "subscribe",
        )
        request = _make_request("announce", message=msg)

        with patch.object(
            handler,
            "_send_confirmation_message",
            new_callable=AsyncMock,
        ):
            response = await handler.handle_message(request)
            await asyncio.sleep(0)

        assert response.status == StatusCode.SUCCESS
        assert "Confirmation sent" in response.meta
        assert store.is_pending("announce", "alice@sender.example")
        store.close()

    async def test_subscribe_already_subscribed(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=["alice@sender.example"])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "subscribe",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        assert "Already subscribed" in response.meta
        store.close()

    async def test_confirm_valid_token(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        token = store.create_token("announce", "alice@sender.example")
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            f"confirm {token}",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        assert "confirmed" in response.meta.lower()
        subscribers = load_subscribers(mailbox_dir / "announce")
        assert "alice@sender.example" in subscribers
        store.close()

    async def test_confirm_invalid_token(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "confirm AAAAAA",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.BAD_REQUEST
        assert "Invalid or expired" in response.meta
        store.close()

    async def test_confirm_wrong_sender(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        token = store.create_token("announce", "alice@sender.example")
        handler = self._make_handler(mailbox_dir, store)

        # Eve tries to confirm Alice's token
        msg = _make_command_message(
            "eve@evil.com",
            "announce@example.com",
            f"confirm {token}",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.BAD_REQUEST
        assert "does not match" in response.meta
        store.close()

    async def test_unsubscribe(self, tmp_path):
        mailbox_dir = _setup_list(
            tmp_path, subscribers=["alice@sender.example", "bob@other.com"]
        )
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "unsubscribe",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        assert "Unsubscribed" in response.meta
        subscribers = load_subscribers(mailbox_dir / "announce")
        assert "alice@sender.example" not in subscribers
        assert "bob@other.com" in subscribers
        store.close()

    async def test_unsubscribe_not_subscribed(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "unsubscribe",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.BAD_REQUEST
        assert "Not subscribed" in response.meta
        store.close()

    async def test_command_not_stored(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "subscribe",
        )
        request = _make_request("announce", message=msg)

        with patch.object(
            handler,
            "_send_confirmation_message",
            new_callable=AsyncMock,
        ):
            await handler.handle_message(request)
            await asyncio.sleep(0)

        files = list((mailbox_dir / "announce").glob("*.gemmail*"))
        assert len(files) == 0
        store.close()

    async def test_command_not_forwarded(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=["alice@sender.example"])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "unsubscribe",
        )
        request = _make_request("announce", message=msg)

        with patch.object(
            handler, "_forward_to_list", new_callable=AsyncMock
        ) as mock_forward:
            await handler.handle_message(request)
            await asyncio.sleep(0)
            assert not mock_forward.called
        store.close()

    async def test_commands_ignored_without_store(self, tmp_path):
        """Without subscription_store, commands flow as normal messages."""
        mailbox_dir = _setup_list(tmp_path, subscribers=["alice@sender.example"])
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=True,
        )

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "subscribe",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)
        # Treated as a normal post, stored successfully
        assert response.status == StatusCode.SUCCESS

    async def test_commands_ignored_when_lists_disabled(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            lists_enabled=False,
            subscription_store=store,
        )

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "subscribe",
        )
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)
        # Treated as normal delivery
        assert response.status == StatusCode.SUCCESS
        store.close()

    async def test_regular_message_flows_normally(self, tmp_path):
        mailbox_dir = _setup_list(tmp_path, subscribers=["alice@sender.example"])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_valid_message("alice@sender.example")
        request = _make_request("announce", message=msg)
        response = await handler.handle_message(request)
        assert response.status == StatusCode.SUCCESS

        files = list((mailbox_dir / "announce").glob("*.gemmail*"))
        assert len(files) >= 1
        store.close()

    async def test_subscribe_with_heading(self, tmp_path):
        """Test that '# subscribe' (gemtext heading) also works."""
        mailbox_dir = _setup_list(tmp_path, subscribers=[])
        store = SubscriptionTokenStore()
        handler = self._make_handler(mailbox_dir, store)

        msg = _make_command_message(
            "alice@sender.example",
            "announce@example.com",
            "# subscribe",
        )
        request = _make_request("announce", message=msg)

        with patch.object(
            handler,
            "_send_confirmation_message",
            new_callable=AsyncMock,
        ):
            response = await handler.handle_message(request)
            await asyncio.sleep(0)

        assert response.status == StatusCode.SUCCESS
        assert "Confirmation sent" in response.meta
        store.close()
