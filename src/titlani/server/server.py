"""Misfin server startup and lifecycle management."""

import asyncio
import tempfile
from pathlib import Path

from tlacacoca import (
    AccessControl,
    AccessControlConfig,
    MiddlewareChain,
    RateLimitConfig,
    RateLimiter,
    configure_logging,
    create_server_context,
    generate_self_signed_cert,
    get_logger,
)

from ..identity.certificate import generate_identity_cert
from .config import ServerConfig
from .handler import FileMailboxHandler
from .protocol import MisfinServerProtocol

logger = get_logger(__name__)


async def start_server(
    config: ServerConfig,
    log_level: str = "INFO",
) -> None:
    """Start a Misfin server."""
    configure_logging(level=log_level)
    config.validate()

    certfile = config.certfile
    keyfile = config.keyfile
    tmp_dir = None

    # Auto-generate server cert if none provided
    if certfile is None or keyfile is None:
        tmp_dir = tempfile.mkdtemp(prefix="titlani_")
        cert_pem, key_pem = generate_self_signed_cert(
            config.hostname, "Titlani Misfin Server"
        )
        certfile = Path(tmp_dir) / "server.pem"
        keyfile = Path(tmp_dir) / "server.key"
        certfile.write_bytes(cert_pem)
        keyfile.write_bytes(key_pem)
        logger.info(
            "auto_generated_server_cert",
            hostname=config.hostname,
        )

    # Auto-generate identity cert if none provided
    identity_certfile = config.identity_certfile
    identity_keyfile = config.identity_keyfile
    if identity_certfile is None or identity_keyfile is None:
        if tmp_dir is None:
            tmp_dir = tempfile.mkdtemp(prefix="titlani_")
        id_cert_pem, id_key_pem = generate_identity_cert(
            mailbox="postmaster",
            hostname=config.hostname,
            blurb=f"Misfin Server ({config.hostname})",
        )
        identity_certfile = Path(tmp_dir) / "identity.pem"
        identity_keyfile = Path(tmp_dir) / "identity.key"
        identity_certfile.write_bytes(id_cert_pem)
        identity_keyfile.write_bytes(id_key_pem)
        logger.info(
            "auto_generated_identity_cert",
            hostname=config.hostname,
        )

    # Create TLS context
    ssl_context = create_server_context(
        certfile=str(certfile),
        keyfile=str(keyfile),
        request_client_cert=True,
    )

    # Build middleware chain
    middlewares = []
    if config.rate_limit_enable:
        rate_config = RateLimitConfig(
            capacity=config.rate_limit_capacity,
            refill_rate=config.rate_limit_refill_rate,
            retry_after=config.rate_limit_retry_after,
        )
        middlewares.append(RateLimiter(rate_config))

    if config.access_control_enable:
        access_config = AccessControlConfig(
            allow_list=config.access_control_allow_list,
            deny_list=config.access_control_deny_list,
            default_allow=config.access_control_default_allow,
        )
        middlewares.append(AccessControl(access_config))

    middleware = MiddlewareChain(middlewares) if middlewares else None

    # Create mailbox directory
    config.mailbox_dir.mkdir(parents=True, exist_ok=True)

    # Create handler
    handler = FileMailboxHandler(
        mailbox_dir=config.mailbox_dir,
        hostname=config.hostname,
    )

    # Start server
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: MisfinServerProtocol(
            message_handler=handler.handle_message,
            middleware=middleware,
        ),
        host=config.host,
        port=config.port,
        ssl=ssl_context,
    )

    logger.info(
        "server_started",
        host=config.host,
        port=config.port,
        hostname=config.hostname,
    )

    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("server_stopped")
