"""End-to-end tests for PROXY protocol support on the Misfin and GMAP listeners.

These start the real server via ``start_server`` and connect over loopback
the way a TCP relay (e.g. Traefik) would: a PROXY v2 header first, then
the TLS handshake. They check that the rate limiter and logs use the client
IP from the header instead of the relay's IP.
"""

import asyncio
import ipaddress
import socket
import ssl
import struct
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from titlani.gmap import protocol as gmap_protocol_module
from titlani.server import protocol as misfin_protocol_module
from titlani.server.config import ServerConfig
from titlani.server.server import start_server

PROXY_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"


def proxy_v2(src: str, src_port: int = 40000, dst_port: int = 1958) -> bytes:
    """Build a PROXY v2 PROXY/TCP header like Traefik sends."""
    src_addr = ipaddress.ip_address(src)
    if src_addr.version == 4:
        fam = 0x11
        dst_addr = ipaddress.ip_address("127.0.0.1")
    else:
        fam = 0x21
        dst_addr = ipaddress.ip_address("::1")
    body = src_addr.packed + dst_addr.packed + struct.pack("!HH", src_port, dst_port)
    return PROXY_V2_SIGNATURE + bytes([0x21, fam]) + struct.pack("!H", len(body)) + body


def proxy_v2_local() -> bytes:
    return PROXY_V2_SIGNATURE + b"\x20\x00\x00\x00"


class RecordingLogger:
    """Stand-in for a module logger that records (event, fields)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, level: str):
        def record(event: str, **kw: Any) -> None:
            self.events.append((event, kw))

        return record

    def client_ips(self, event: str) -> list[str]:
        return [kw.get("client_ip", "") for name, kw in self.events if name == event]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _misfin_request(body: str = "Hello through the relay\n") -> bytes:
    message = f"sender@client.example.com Sender\nalice@localhost\n\n# Hi\n\n{body}"
    raw = message.encode()
    return f"misfin://alice@localhost\t{len(raw)}\r\n".encode() + raw


class _MemoryBIOClient:
    """Blocking TLS client over a raw socket using ssl.MemoryBIO.

    Driving TLS by hand lets the PROXY header and the ClientHello go out in
    a single ``send()``, the way a relay usually forwards them.
    """

    def __init__(self, port: int, prefix: bytes) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # test server uses a self-signed cert
        self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        self.tls = ctx.wrap_bio(self.incoming, self.outgoing, server_side=False)
        self.pending = prefix

    def flush(self) -> None:
        data = self.pending + self.outgoing.read()
        self.pending = b""
        if data:
            self.sock.sendall(data)

    def pump(self) -> bool:
        chunk = self.sock.recv(65536)
        if chunk:
            self.incoming.write(chunk)
        return bool(chunk)

    def handshake(self) -> None:
        while True:
            try:
                self.tls.do_handshake()
                return
            except ssl.SSLWantReadError:
                self.flush()
                if not self.pump():
                    raise ConnectionError("server closed during handshake") from None

    def read_line(self) -> bytes:
        response = b""
        while b"\r\n" not in response:
            try:
                chunk = self.tls.read(65536)
            except ssl.SSLWantReadError:
                if not self.pump():
                    break
                continue
            except (ssl.SSLZeroReturnError, ssl.SSLEOFError):
                break
            if not chunk:
                break
            response += chunk
        return response


def _tls_exchange(port: int, prefix: bytes, payload: bytes) -> bytes:
    """Send ``prefix`` + ClientHello together, then ``payload`` over TLS.

    Returns the server's first response line.
    """
    client = _MemoryBIOClient(port, prefix)
    try:
        client.handshake()
        client.tls.write(payload)
        client.flush()
        return client.read_line()
    finally:
        client.sock.close()


async def _send(port: int, prefix: bytes, payload: bytes | None = None) -> int:
    """Return the numeric status from the server's response line."""
    response = await asyncio.to_thread(
        _tls_exchange, port, prefix, payload or _misfin_request()
    )
    return int(response.split(b" ", 1)[0])


async def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.05)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise TimeoutError(f"server did not start on port {port}")


@pytest.fixture
def ports() -> tuple[int, int]:
    return _free_port(), _free_port()


@pytest.fixture
def misfin_log(monkeypatch) -> RecordingLogger:
    recorder = RecordingLogger()
    monkeypatch.setattr(misfin_protocol_module, "logger", recorder)
    return recorder


@pytest.fixture
def gmap_log(monkeypatch) -> RecordingLogger:
    recorder = RecordingLogger()
    monkeypatch.setattr(gmap_protocol_module, "logger", recorder)
    return recorder


def _config(tmp_path: Path, ports: tuple[int, int], proxy: bool) -> ServerConfig:
    mailbox_dir = tmp_path / "mailboxes"
    (mailbox_dir / "alice").mkdir(parents=True)
    return ServerConfig(
        server={
            "host": "127.0.0.1",
            "port": ports[0],
            "hostname": "localhost",
            "mailbox_dir": mailbox_dir,
        },
        # One message per client IP, effectively no refill during the test.
        rate_limit={"enable": True, "capacity": 1, "refill_rate": 0.001},
        gmap={"enable": True, "port": ports[1]},
        proxy_protocol={"enable": proxy, "trusted_sources": ["127.0.0.0/8"]},
    )


async def _run(config: ServerConfig) -> AsyncIterator[None]:
    task = asyncio.create_task(start_server(config, log_level="WARNING"))
    try:
        await _wait_for_port(config.server.port)
        await _wait_for_port(config.gmap.port)
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.fixture
async def proxied_server(tmp_path, ports) -> AsyncIterator[ServerConfig]:
    config = _config(tmp_path, ports, proxy=True)
    async for _ in _run(config):
        yield config


@pytest.fixture
async def direct_server(tmp_path, ports) -> AsyncIterator[ServerConfig]:
    config = _config(tmp_path, ports, proxy=False)
    async for _ in _run(config):
        yield config


@pytest.mark.integration
@pytest.mark.timeout(20)
class TestProxyProtocolEndToEnd:
    async def test_rate_limit_keyed_by_proxied_client_ip(
        self, proxied_server: ServerConfig, misfin_log: RecordingLogger
    ):
        port = proxied_server.server.port
        assert await _send(port, proxy_v2("203.0.113.1")) == 20
        # Same client again: its own bucket is now empty.
        assert await _send(port, proxy_v2("203.0.113.1")) == 44
        # Different clients behind the same relay get their own buckets.
        assert await _send(port, proxy_v2("203.0.113.2")) == 20
        assert await _send(port, proxy_v2("2001:db8::77")) == 20

        assert misfin_log.client_ips("middleware_denied") == ["203.0.113.1"]
        connected = misfin_log.client_ips("connection_established")
        assert connected == ["203.0.113.1", "203.0.113.1", "203.0.113.2", "2001:db8::77"]
        assert "127.0.0.1" not in {
            kw.get("client_ip") for _, kw in misfin_log.events if "client_ip" in kw
        }

        delivered = list((proxied_server.server.mailbox_dir / "alice").glob("*.gemmail*"))
        assert len(delivered) == 3

    async def test_without_proxy_protocol_all_clients_share_relay_bucket(
        self, direct_server: ServerConfig, misfin_log: RecordingLogger
    ):
        """Control: without PROXY support, everyone looks like the relay."""
        port = direct_server.server.port
        assert await _send(port, b"") == 20
        assert await _send(port, b"") == 44
        assert misfin_log.client_ips("middleware_denied") == ["127.0.0.1"]

    async def test_local_header_uses_relay_address(
        self, proxied_server: ServerConfig, misfin_log: RecordingLogger
    ):
        assert await _send(proxied_server.server.port, proxy_v2_local()) == 20
        assert misfin_log.client_ips("connection_established") == ["127.0.0.1"]

    async def test_trusted_relay_without_header_rejected(
        self, proxied_server: ServerConfig, misfin_log: RecordingLogger
    ):
        with pytest.raises(ConnectionError):
            await _send(proxied_server.server.port, b"")
        assert misfin_log.client_ips("connection_established") == []

    async def test_gmap_listener_uses_proxied_client_ip(
        self, proxied_server: ServerConfig, gmap_log: RecordingLogger
    ):
        await asyncio.to_thread(
            _tls_exchange,
            proxied_server.gmap.port,
            proxy_v2("198.51.100.23", dst_port=1960),
            b"gemini://localhost/\r\n",
        )
        assert gmap_log.client_ips("gmap_connection_established") == ["198.51.100.23"]

    async def test_gmap_listener_requires_header_from_relay(
        self, proxied_server: ServerConfig, gmap_log: RecordingLogger
    ):
        with pytest.raises(ConnectionError):
            await asyncio.to_thread(
                _tls_exchange, proxied_server.gmap.port, b"", b"gemini://localhost/\r\n"
            )
        assert gmap_log.client_ips("gmap_connection_established") == []
