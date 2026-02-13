"""SPKI-based sender verification.

Verifies senders by connecting to their server, extracting the TLS
certificate's Subject Public Key Info (SPKI) hash, and comparing it
against a cached value.  This is a TOFU model for server identity —
cryptographically stronger than probe-based verification.
"""

import asyncio
import hashlib
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from tlacacoca import get_logger

from ..content.gemmail import MisfinAddress
from ..protocol.constants import DEFAULT_PORT
from .cache import SenderVerificationCache
from .verifier import VerificationResult

logger = get_logger(__name__)


def extract_spki_hash(cert: x509.Certificate) -> str:
    """Return the SHA-256 hex digest of a certificate's SPKI bytes."""
    spki_der = cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(spki_der).hexdigest()


class SPKIVerifier:
    """Verify senders by caching their server's SPKI hash (TOFU model).

    On first contact with a server, connects via TLS, extracts the SPKI
    hash, and caches it.  While the cache entry is valid (within TTL),
    subsequent verifications return immediately without a network call.
    When the entry expires, the server is re-checked and its current
    SPKI compared against the last known value.
    """

    def __init__(
        self,
        cache: SenderVerificationCache,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
        on_spki_change: str = "reject",
    ) -> None:
        self.cache = cache
        self.port = port
        self.timeout = timeout
        self.on_spki_change = on_spki_change

    async def verify_sender(self, address: MisfinAddress) -> VerificationResult:
        hostname = address.hostname

        # Cache hit — no network call needed
        cached_spki = self.cache.get_server_spki(hostname)
        if cached_spki is not None:
            logger.debug("spki_cache_hit", hostname=hostname)
            return VerificationResult(verified=True, fingerprint=cached_spki, cached=True)

        # Cache miss — connect to server
        try:
            current_spki = await self._fetch_server_spki(hostname)
        except TimeoutError:
            logger.warning("spki_connection_timeout", hostname=hostname)
            return VerificationResult(verified=False, reason="Connection timed out")
        except Exception as e:
            logger.error("spki_connection_error", hostname=hostname, error=str(e))
            return VerificationResult(verified=False, reason=f"Connection error: {e}")

        if current_spki is None:
            return VerificationResult(verified=False, reason="No peer certificate")

        # Compare against last known SPKI (even if expired) to detect
        # key changes when re-verifying after TTL expiry.
        last_known = self.cache.get_last_server_spki(hostname)

        if last_known is None:
            # True first contact — TOFU
            self.cache.add_server_spki(hostname, current_spki)
            logger.info(
                "spki_first_verified",
                hostname=hostname,
                spki=current_spki[:16] + "...",
            )
            return VerificationResult(verified=True, fingerprint=current_spki)

        if current_spki == last_known:
            # Same key, just refresh the timestamp
            self.cache.add_server_spki(hostname, current_spki)
            return VerificationResult(verified=True, fingerprint=current_spki)

        # SPKI changed since last verification
        return self._handle_spki_change(hostname, last_known, current_spki)

    def _handle_spki_change(
        self, hostname: str, old_spki: str, new_spki: str
    ) -> VerificationResult:
        if self.on_spki_change == "accept":
            logger.warning(
                "spki_key_change_accepted",
                hostname=hostname,
                old=old_spki[:16] + "...",
                new=new_spki[:16] + "...",
            )
            self.cache.add_server_spki(hostname, new_spki)
            return VerificationResult(verified=True, fingerprint=new_spki)

        logger.warning(
            "spki_key_change_rejected",
            hostname=hostname,
            old=old_spki[:16] + "...",
            new=new_spki[:16] + "...",
        )
        return VerificationResult(verified=False, reason="Server SPKI changed")

    async def _fetch_server_spki(self, hostname: str) -> str | None:
        """Connect to *hostname* via TLS and return its SPKI hash."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                hostname,
                self.port,
                ssl=ctx,
                server_hostname=hostname,
            ),
            timeout=self.timeout,
        )
        try:
            ssl_obj = writer.get_extra_info("ssl_object")
            if ssl_obj is None:
                return None
            der_cert = ssl_obj.getpeercert(binary_form=True)
            if der_cert is None:
                return None
            cert = x509.load_der_x509_certificate(der_cert)
            return extract_spki_hash(cert)
        finally:
            writer.close()
            await writer.wait_closed()
