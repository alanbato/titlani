"""End-to-end integration test: client sends message to server."""

import asyncio
import ssl
from pathlib import Path

import pytest
from tlacacoca import (
    TLSServerProtocol,
    create_permissive_server_context,
    generate_self_signed_cert,
)

from titlani.client.protocol import MisfinClientProtocol
from titlani.content.gemmail import GemmailMessage, MisfinAddress
from titlani.protocol.request import MisfinRequest
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode
from titlani.server.handler import FileMailboxHandler
from titlani.server.protocol import MisfinServerProtocol


@pytest.fixture
def server_certs(tmp_path: Path) -> tuple[Path, Path]:
    """Generate server TLS certificates."""
    cert_pem, key_pem = generate_self_signed_cert("localhost", "Test Server")
    cert_path = tmp_path / "server.pem"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    return cert_path, key_path


@pytest.fixture
def mailbox_dir(tmp_path: Path) -> Path:
    """Create a mailbox directory structure."""
    mailbox = tmp_path / "mailboxes" / "alice"
    mailbox.mkdir(parents=True)
    return tmp_path / "mailboxes"


def _make_client_ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


async def _send_raw(
    host: str,
    port: int,
    request: MisfinRequest,
    ssl_ctx: ssl.SSLContext,
) -> MisfinResponse:
    """Low-level send that connects to a specific host:port."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    request_bytes = request.to_bytes()
    protocol = MisfinClientProtocol(request_bytes, future)

    transport, protocol = await asyncio.wait_for(
        loop.create_connection(
            lambda: protocol,
            host=host,
            port=port,
            ssl=ssl_ctx,
            server_hostname=host,
        ),
        timeout=5.0,
    )
    try:
        return await asyncio.wait_for(future, timeout=5.0)
    finally:
        transport.close()


def _build_message(
    to_mailbox: str,
    to_hostname: str,
    body: str,
    subject: str | None = None,
    sender: MisfinAddress | None = None,
) -> MisfinRequest:
    """Build a MisfinRequest with a proper GemmailMessage."""
    from datetime import UTC, datetime

    recipient = MisfinAddress(mailbox=to_mailbox, hostname=to_hostname)
    full_body = ""
    if subject:
        full_body = f"# {subject}\n\n"
    full_body += body
    if not full_body.endswith("\n"):
        full_body += "\n"

    msg = GemmailMessage(
        senders=[sender] if sender else [],
        recipients=[recipient],
        timestamps=[datetime.now(UTC)],
        body=full_body,
    )
    msg_bytes = msg.to_bytes()
    return MisfinRequest(
        mailbox=to_mailbox,
        hostname=to_hostname,
        content_length=len(msg_bytes),
        raw_message=msg_bytes,
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
async def test_client_server_e2e(
    server_certs: tuple[Path, Path],
    mailbox_dir: Path,
    unused_tcp_port: int,
):
    """Test full client -> server message delivery."""
    server_cert, server_key = server_certs

    ssl_context = create_permissive_server_context(
        certfile=str(server_cert),
        keyfile=str(server_key),
        request_client_cert=True,
    )

    handler = FileMailboxHandler(
        mailbox_dir=mailbox_dir,
        hostname="localhost",
    )

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: TLSServerProtocol(
            lambda: MisfinServerProtocol(
                message_handler=handler.handle_message,
            ),
            ssl_context,
        ),
        host="127.0.0.1",
        port=unused_tcp_port,
    )

    try:
        sender = MisfinAddress(
            mailbox="sender",
            hostname="client.example.com",
            blurb="Test Sender",
        )
        request = _build_message(
            to_mailbox="alice",
            to_hostname="localhost",
            body="This is a test.",
            subject="Test Message",
            sender=sender,
        )
        response = await _send_raw(
            "127.0.0.1",
            unused_tcp_port,
            request,
            _make_client_ssl(),
        )

        assert response.status == StatusCode.SUCCESS

        files = list((mailbox_dir / "alice").glob("*.gemmail.new"))
        assert len(files) == 1

        msg = GemmailMessage.from_bytes(files[0].read_bytes())
        assert msg.subject == "Test Message"
        assert len(msg.senders) == 1
        assert msg.senders[0].mailbox == "sender"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.integration
@pytest.mark.timeout(10)
async def test_server_rejects_unknown_mailbox(
    server_certs: tuple[Path, Path],
    mailbox_dir: Path,
    unused_tcp_port: int,
):
    """Test that server returns 51 for unknown mailbox."""
    server_cert, server_key = server_certs

    ssl_context = create_permissive_server_context(
        certfile=str(server_cert),
        keyfile=str(server_key),
        request_client_cert=True,
    )

    handler = FileMailboxHandler(
        mailbox_dir=mailbox_dir,
        hostname="localhost",
    )

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: TLSServerProtocol(
            lambda: MisfinServerProtocol(
                message_handler=handler.handle_message,
            ),
            ssl_context,
        ),
        host="127.0.0.1",
        port=unused_tcp_port,
    )

    try:
        request = _build_message(
            to_mailbox="nonexistent",
            to_hostname="localhost",
            body="Hello",
        )
        response = await _send_raw(
            "127.0.0.1",
            unused_tcp_port,
            request,
            _make_client_ssl(),
        )
        assert response.status == StatusCode.MAILBOX_NOT_FOUND
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.integration
@pytest.mark.timeout(10)
async def test_server_rejects_wrong_domain(
    server_certs: tuple[Path, Path],
    mailbox_dir: Path,
    unused_tcp_port: int,
):
    """Test that server returns 53 for wrong domain."""
    server_cert, server_key = server_certs

    ssl_context = create_permissive_server_context(
        certfile=str(server_cert),
        keyfile=str(server_key),
        request_client_cert=True,
    )

    handler = FileMailboxHandler(
        mailbox_dir=mailbox_dir,
        hostname="localhost",
    )

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: TLSServerProtocol(
            lambda: MisfinServerProtocol(
                message_handler=handler.handle_message,
            ),
            ssl_context,
        ),
        host="127.0.0.1",
        port=unused_tcp_port,
    )

    try:
        # Connect to localhost but claim wrong domain in request
        request = _build_message(
            to_mailbox="alice",
            to_hostname="wrongdomain.com",
            body="Hello",
        )
        response = await _send_raw(
            "127.0.0.1",
            unused_tcp_port,
            request,
            _make_client_ssl(),
        )
        assert response.status == StatusCode.DOMAIN_NOT_SERVICED
    finally:
        server.close()
        await server.wait_closed()
