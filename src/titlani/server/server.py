"""Misfin server startup and lifecycle management."""

import asyncio
import os
import shutil
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

from ..encryption.manager import EncryptionManager
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

_gmap_available = True
try:
    from ..gmap.handler import GmapHandler
    from ..gmap.protocol import GeminiServerProtocol
except ImportError:
    _gmap_available = False

logger = get_logger(__name__)


def _load_recipient_fingerprints(
    cert_dir: Path,
    fallback_fingerprint: str,
) -> dict[str, str]:
    """Scan for per-mailbox identity certs (<mailbox>.pem) and compute fingerprints.

    Returns a dict mapping mailbox name to normalized fingerprint.
    """
    fingerprints: dict[str, str] = {}
    if not cert_dir.is_dir():
        return fingerprints

    for pem_file in cert_dir.glob("*.pem"):
        mailbox = pem_file.stem
        try:
            cert = load_pem_x509_certificate(pem_file.read_bytes())
            fp = normalize_fingerprint(get_certificate_fingerprint(cert))
            fingerprints[mailbox] = fp
            logger.info(
                "recipient_cert_loaded",
                mailbox=mailbox,
                fingerprint=fp[:16] + "...",
            )
        except Exception:
            logger.warning(
                "recipient_cert_load_failed",
                mailbox=mailbox,
                path=str(pem_file),
            )
    return fingerprints


def _setup_encryption(
    config: ServerConfig,
) -> EncryptionManager | None:
    if not config.encryption_enable:
        return None

    manager = EncryptionManager(config.mailbox_dir)
    key_dir = config.encryption_key_dir or config.mailbox_dir

    for entry in config.mailbox_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            pub_path = key_dir / f"{entry.name}.enc.pub"
            if pub_path.exists():
                manager.load_public_key_for_mailbox(entry.name, pub_path)
                logger.info(
                    "encryption_key_loaded",
                    mailbox=entry.name,
                )
            else:
                logger.warning(
                    "encryption_no_key",
                    mailbox=entry.name,
                    key_path=str(pub_path),
                )
    return manager


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

    # Set up encryption if enabled
    encryption_manager = _setup_encryption(config)

    # Load per-mailbox recipient fingerprints
    cert_dir = config.identity_cert_dir or config.mailbox_dir
    recipient_fps = _load_recipient_fingerprints(cert_dir, id_fingerprint)

    def _get_recipient_fingerprint(mailbox: str) -> str | None:
        return recipient_fps.get(mailbox, id_fingerprint)

    # Create base handler
    handler: FileMailboxHandler | VerifyingHandler = FileMailboxHandler(
        mailbox_dir=config.mailbox_dir,
        hostname=config.hostname,
        recipient_fingerprint_fn=_get_recipient_fingerprint,
        identity_cert_fingerprint=id_fingerprint,
        encryption_manager=encryption_manager,
        auto_reply_enabled=config.auto_reply_enable,
        auto_reply_interval=config.auto_reply_interval,
        identity_certfile=identity_certfile,
        identity_keyfile=identity_keyfile,
        port=config.port,
    )

    # Wrap with verification if mode is not "off"
    cache: SenderVerificationCache | None = None
    if config.verification_mode != "off":
        cache_path = config.verification_cache_path
        if cache_path is None:
            cache_path = config.mailbox_dir / "verification_cache.db"
        cache = SenderVerificationCache(
            cache_path, ttl_seconds=config.verification_cache_ttl
        )

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

    # Misfin protocol factory (main port, no client certs)
    def misfin_protocol_factory() -> MisfinServerProtocol:
        return MisfinServerProtocol(
            message_handler=handler.handle_message,
            middleware=middleware,
        )

    # Start server(s)
    loop = asyncio.get_running_loop()
    misfin_server = await loop.create_server(
        misfin_protocol_factory,
        host=config.host,
        port=config.port,
        ssl=ssl_context,
    )

    logger.info(
        "server_started",
        host=config.host,
        port=config.port,
        hostname=config.hostname,
        rate_limiting=config.rate_limit_enable,
        access_control=config.access_control_enable,
        encryption=config.encryption_enable,
        gmap=config.gmap_enable,
        mailbox_dir=str(config.mailbox_dir),
    )

    gmap_server = None
    if config.gmap_enable and _gmap_available:
        # Collect per-mailbox .pem paths for client_ca_certs
        client_ca_certs = [str(p) for p in cert_dir.glob("*.pem") if p.is_file()]

        if not client_ca_certs:
            logger.warning(
                "gmap_no_client_certs",
                cert_dir=str(cert_dir),
                message=(
                    "GMAP enabled but no per-mailbox .pem files found. "
                    "Use 'titlani identity generate --install' to set up "
                    "user certificates."
                ),
            )

        gmap_ssl_context = create_server_context(
            certfile=str(certfile),
            keyfile=str(keyfile),
            request_client_cert=True,
            client_ca_certs=client_ca_certs or None,
        )

        gmap_handler = GmapHandler(
            mailbox_dir=config.mailbox_dir,
            hostname=config.hostname,
            recipient_fps=recipient_fps,
        )

        def gmap_protocol_factory() -> GeminiServerProtocol:
            return GeminiServerProtocol(
                request_handler=gmap_handler.handle_request,
            )

        gmap_server = await loop.create_server(
            gmap_protocol_factory,
            host=config.host,
            port=config.gmap_port,
            ssl=gmap_ssl_context,
        )

        logger.info(
            "gmap_enabled",
            port=config.gmap_port,
            client_certs=len(client_ca_certs),
        )

    try:
        if gmap_server is not None:
            async with misfin_server, gmap_server:
                await asyncio.gather(
                    misfin_server.serve_forever(),
                    gmap_server.serve_forever(),
                )
        else:
            async with misfin_server:
                await misfin_server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        if cache is not None:
            cache.close()
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("server_stopped")
