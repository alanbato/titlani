"""Misfin server startup and lifecycle management."""

import asyncio
import os
from pathlib import Path

from cryptography.x509 import load_pem_x509_certificate
from tlacacoca import (
    AccessControl,
    AccessControlConfig,
    MiddlewareChain,
    RateLimitConfig,
    RateLimiter,
    TLSServerProtocol,
    configure_logging,
    create_permissive_server_context,
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
    CombinedVerifier,
    ProbeVerifier,
    SenderVerificationCache,
    SPKIVerifier,
    VerificationMethod,
    VerificationMode,
    VerifyingHandler,
)
from .config import ServerConfig
from .handler import FileMailboxHandler
from .protocol import MisfinServerProtocol
from .subscription import SubscriptionTokenStore

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
    if not config.encryption.enable:
        return None

    manager = EncryptionManager(config.server.mailbox_dir)
    key_dir = config.encryption.key_dir or config.server.mailbox_dir

    for entry in config.server.mailbox_dir.iterdir():
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


def _ensure_certificates(
    config: ServerConfig,
) -> tuple[Path, Path, Path, Path]:
    """Ensure server and identity certificates exist, auto-generating if needed.

    When certfile/keyfile are set in config but don't exist on disk, generates
    them at those exact paths.  When they are None (legacy configs), falls back
    to generating inside ``mailbox_dir/.auto-certs/``.

    Returns (certfile, keyfile, identity_certfile, identity_keyfile).
    """
    certfile = config.server.certfile
    keyfile = config.server.keyfile

    if certfile is not None and keyfile is not None:
        # Config specifies paths — generate only if the files are missing
        if not certfile.exists() or not keyfile.exists():
            certfile.parent.mkdir(parents=True, exist_ok=True)
            keyfile.parent.mkdir(parents=True, exist_ok=True)
            cert_pem, key_pem = generate_self_signed_cert(
                config.server.hostname, "Titlani Misfin Server"
            )
            certfile.write_bytes(cert_pem)
            keyfile.write_bytes(key_pem)
            os.chmod(keyfile, 0o600)
            logger.info(
                "auto_generated_server_cert",
                hostname=config.server.hostname,
                certfile=str(certfile),
            )
    else:
        # No cert paths in config — use a stable directory alongside mailboxes
        auto_dir = config.server.mailbox_dir / ".auto-certs"
        auto_dir.mkdir(parents=True, exist_ok=True)
        certfile = auto_dir / "server.pem"
        keyfile = auto_dir / "server.key"
        if not certfile.exists() or not keyfile.exists():
            cert_pem, key_pem = generate_self_signed_cert(
                config.server.hostname, "Titlani Misfin Server"
            )
            certfile.write_bytes(cert_pem)
            keyfile.write_bytes(key_pem)
            os.chmod(keyfile, 0o600)
            logger.info(
                "auto_generated_server_cert",
                hostname=config.server.hostname,
                certfile=str(certfile),
            )

    identity_certfile = config.server.identity_certfile
    identity_keyfile = config.server.identity_keyfile

    if identity_certfile is not None and identity_keyfile is not None:
        if not identity_certfile.exists() or not identity_keyfile.exists():
            identity_certfile.parent.mkdir(parents=True, exist_ok=True)
            identity_keyfile.parent.mkdir(parents=True, exist_ok=True)
            id_cert_pem, id_key_pem = generate_identity_cert(
                mailbox="postmaster",
                hostname=config.server.hostname,
                blurb=f"Misfin Server ({config.server.hostname})",
            )
            identity_certfile.write_bytes(id_cert_pem)
            identity_keyfile.write_bytes(id_key_pem)
            os.chmod(identity_keyfile, 0o600)
            logger.info(
                "auto_generated_identity_cert",
                hostname=config.server.hostname,
                certfile=str(identity_certfile),
            )
    else:
        auto_dir = config.server.mailbox_dir / ".auto-certs"
        auto_dir.mkdir(parents=True, exist_ok=True)
        identity_certfile = auto_dir / "identity.pem"
        identity_keyfile = auto_dir / "identity.key"
        if not identity_certfile.exists() or not identity_keyfile.exists():
            id_cert_pem, id_key_pem = generate_identity_cert(
                mailbox="postmaster",
                hostname=config.server.hostname,
                blurb=f"Misfin Server ({config.server.hostname})",
            )
            identity_certfile.write_bytes(id_cert_pem)
            identity_keyfile.write_bytes(id_key_pem)
            os.chmod(identity_keyfile, 0o600)
            logger.info(
                "auto_generated_identity_cert",
                hostname=config.server.hostname,
                certfile=str(identity_certfile),
            )

    return certfile, keyfile, identity_certfile, identity_keyfile


def _build_middleware(config: ServerConfig) -> MiddlewareChain | None:
    """Build middleware chain from server config."""
    middlewares = []
    if config.rate_limit.enable:
        rate_config = RateLimitConfig(
            capacity=config.rate_limit.capacity,
            refill_rate=config.rate_limit.refill_rate,
            retry_after=config.rate_limit.retry_after,
        )
        middlewares.append(RateLimiter(rate_config))

    if config.access_control.enable:
        access_config = AccessControlConfig(
            allow_list=config.access_control.allow_list,
            deny_list=config.access_control.deny_list,
            default_allow=config.access_control.default_allow,
        )
        middlewares.append(AccessControl(access_config))

    return MiddlewareChain(middlewares) if middlewares else None


def _setup_verification(
    config: ServerConfig,
    handler: FileMailboxHandler,
    identity_certfile: Path,
    identity_keyfile: Path,
) -> tuple[FileMailboxHandler | VerifyingHandler, SenderVerificationCache | None]:
    """Wrap handler with sender verification if configured."""
    if config.verification.mode == "off":
        return handler, None

    cache_path = config.verification.cache_path
    if cache_path is None:
        cache_path = config.server.mailbox_dir / "verification_cache.db"
    cache = SenderVerificationCache(cache_path, ttl_seconds=config.verification.cache_ttl)

    method = VerificationMethod(config.verification.method)

    verifier: ProbeVerifier | SPKIVerifier | CombinedVerifier
    if method == VerificationMethod.SPKI:
        verifier = SPKIVerifier(
            cache=cache,
            port=config.server.port,
            timeout=config.verification.probe_timeout,
            on_spki_change=config.verification.spki_on_change,
        )
    elif method == VerificationMethod.PROBE_SPKI:
        probe = ProbeVerifier(
            cache=cache,
            identity_cert=identity_certfile,
            identity_key=identity_keyfile,
            port=config.server.port,
            timeout=config.verification.probe_timeout,
        )
        spki = SPKIVerifier(
            cache=cache,
            port=config.server.port,
            timeout=config.verification.probe_timeout,
            on_spki_change=config.verification.spki_on_change,
        )
        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
    else:
        verifier = ProbeVerifier(
            cache=cache,
            identity_cert=identity_certfile,
            identity_key=identity_keyfile,
            port=config.server.port,
            timeout=config.verification.probe_timeout,
        )

    verified_handler = VerifyingHandler(
        wrapped=handler,
        verifier=verifier,
        mode=VerificationMode(config.verification.mode),
        method=method,
    )
    logger.info(
        "sender_verification_enabled",
        mode=config.verification.mode,
        method=config.verification.method,
    )
    return verified_handler, cache


async def _start_gmap_server(
    config: ServerConfig,
    certfile: Path,
    keyfile: Path,
    cert_dir: Path,
    recipient_fps: dict[str, str],
) -> asyncio.Server | None:
    """Start the GMAP server if enabled and available."""
    if not config.gmap.enable or not _gmap_available:
        return None

    gmap_ssl_context = create_permissive_server_context(
        certfile=str(certfile),
        keyfile=str(keyfile),
        request_client_cert=True,
    )

    gmap_handler = GmapHandler(
        mailbox_dir=config.server.mailbox_dir,
        hostname=config.server.hostname,
        recipient_fps=recipient_fps,
    )

    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: TLSServerProtocol(
            lambda: GeminiServerProtocol(
                request_handler=gmap_handler.handle_request,
            ),
            gmap_ssl_context,
        ),
        host=config.server.host,
        port=config.gmap.port,
    )

    logger.info(
        "gmap_enabled",
        port=config.gmap.port,
    )
    return server


async def start_server(
    config: ServerConfig,
    log_level: str = "INFO",
) -> None:
    """Start a Misfin server."""
    configure_logging(log_level=log_level)
    config.validate_files()

    certfile, keyfile, identity_certfile, identity_keyfile = _ensure_certificates(config)

    # Create TLS context using PyOpenSSL-based permissive context that
    # accepts any client cert (including self-signed) without CA validation.
    # Client identity is verified at the application layer via TOFU.
    ssl_context = create_permissive_server_context(
        certfile=str(certfile),
        keyfile=str(keyfile),
        request_client_cert=True,
    )

    middleware = _build_middleware(config)

    # Create mailbox directory with restrictive permissions
    config.server.mailbox_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config.server.mailbox_dir, 0o700)

    # Compute identity certificate fingerprint for probe responses
    id_cert = load_pem_x509_certificate(identity_certfile.read_bytes())
    id_fingerprint = normalize_fingerprint(get_certificate_fingerprint(id_cert))

    # Set up encryption if enabled
    encryption_manager = _setup_encryption(config)

    # Load per-mailbox recipient fingerprints
    cert_dir = config.server.identity_cert_dir or config.server.mailbox_dir
    recipient_fps = _load_recipient_fingerprints(cert_dir, id_fingerprint)

    # Create subscription token store for mailing lists
    subscription_store: SubscriptionTokenStore | None = None
    if config.lists.enable:
        from .lists import SUBSCRIPTION_DB_FILE

        subscription_store = SubscriptionTokenStore(
            config.server.mailbox_dir / SUBSCRIPTION_DB_FILE
        )

    # Create base handler
    base_handler = FileMailboxHandler(
        mailbox_dir=config.server.mailbox_dir,
        hostname=config.server.hostname,
        recipient_fingerprint_fn=lambda m: recipient_fps.get(m, id_fingerprint),
        identity_cert_fingerprint=id_fingerprint,
        encryption_manager=encryption_manager,
        auto_reply_enabled=config.auto_reply.enable,
        auto_reply_interval=config.auto_reply.interval,
        identity_certfile=identity_certfile,
        identity_keyfile=identity_keyfile,
        port=config.server.port,
        lists_enabled=config.lists.enable,
        lists_archive=config.lists.archive,
        subscription_store=subscription_store,
    )

    handler, cache = _setup_verification(
        config, base_handler, identity_certfile, identity_keyfile
    )

    # Start Misfin server — TLS handled by TLSServerProtocol (no ssl= param)
    loop = asyncio.get_running_loop()
    misfin_server = await loop.create_server(
        lambda: TLSServerProtocol(
            lambda: MisfinServerProtocol(
                message_handler=handler.handle_message,
                middleware=middleware,
            ),
            ssl_context,
        ),
        host=config.server.host,
        port=config.server.port,
    )

    logger.info(
        "server_started",
        host=config.server.host,
        port=config.server.port,
        hostname=config.server.hostname,
        rate_limiting=config.rate_limit.enable,
        access_control=config.access_control.enable,
        encryption=config.encryption.enable,
        gmap=config.gmap.enable,
        mailbox_dir=str(config.server.mailbox_dir),
    )

    gmap_server = await _start_gmap_server(
        config, certfile, keyfile, cert_dir, recipient_fps
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
        if subscription_store is not None:
            subscription_store.close()
        logger.info("server_stopped")
