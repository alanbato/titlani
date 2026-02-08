"""Misfin server startup and lifecycle management."""

import asyncio
import os
import tempfile
from pathlib import Path

from cryptography.x509 import load_pem_x509_certificate
from tlacacoca import (
    AccessControl,
    AccessControlConfig,
    MiddlewareChain,
    RateLimitConfig,
    RateLimiter,
    configure_logging,
    create_server_context,
    generate_self_signed_cert,
    get_certificate_fingerprint,
    get_logger,
)

from ..identity.certificate import (
    generate_identity_cert,
    normalize_fingerprint,
)
from ..verification import (
    ProbeVerifier,
    SenderVerificationCache,
    VerificationMode,
    VerifyingHandler,
)
from .config import ServerConfig
from .handler import FileMailboxHandler
from .protocol import MisfinServerProtocol

logger = get_logger(__name__)


async def start_server(
    config: ServerConfig,
    log_level: str = "INFO",
) -> None:
    """Start a Misfin server."""
    configure_logging(log_level=log_level)
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
        os.chmod(keyfile, 0o600)
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
        os.chmod(identity_keyfile, 0o600)
        logger.info(
            "auto_generated_identity_cert",
            hostname=config.hostname,
        )

    # Create TLS context
    # NOTE: request_client_cert=False because OpenSSL 3.x with CERT_OPTIONAL
    # rejects self-signed client certs (no CA to verify against), causing
    # silent TLS handshake failures. Sender identity is carried in the
    # gemmail message metadata instead.
    ssl_context = create_server_context(
        certfile=str(certfile),
        keyfile=str(keyfile),
        request_client_cert=False,
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

    # Create mailbox directory with restrictive permissions
    config.mailbox_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config.mailbox_dir, 0o700)

    # Compute identity certificate fingerprint for probe responses
    id_cert = load_pem_x509_certificate(identity_certfile.read_bytes())
    id_fingerprint = normalize_fingerprint(get_certificate_fingerprint(id_cert))

    # Create base handler
    handler: FileMailboxHandler | VerifyingHandler = FileMailboxHandler(
        mailbox_dir=config.mailbox_dir,
        hostname=config.hostname,
        identity_cert_fingerprint=id_fingerprint,
    )

    # Wrap with verification if mode is not "off"
    if config.verification_mode != "off":
        cache_path = config.verification_cache_path
        if cache_path is None:
            cache_path = config.mailbox_dir / "verification_cache.db"
        cache = SenderVerificationCache(cache_path)

        verifier = ProbeVerifier(
            cache=cache,
            identity_cert=identity_certfile,
            identity_key=identity_keyfile,
            port=config.port,
            timeout=config.verification_probe_timeout,
        )
        handler = VerifyingHandler(
            wrapped=handler,
            verifier=verifier,
            mode=VerificationMode(config.verification_mode),
        )
        logger.info(
            "sender_verification_enabled",
            mode=config.verification_mode,
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
