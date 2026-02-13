"""Probe-based sender verification."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tlacacoca import get_logger

from ..client.session import MisfinClient
from ..content.gemmail import MisfinAddress
from ..identity.certificate import normalize_fingerprint
from ..protocol.constants import DEFAULT_PORT
from ..protocol.request import MisfinRequest
from ..protocol.status import is_success
from .cache import SenderVerificationCache

logger = get_logger(__name__)


class VerificationMode(StrEnum):
    OFF = "off"
    OPTIONAL = "optional"
    REQUIRED = "required"


class VerificationMethod(StrEnum):
    PROBE = "probe"
    SPKI = "spki"


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    fingerprint: str | None = None
    cached: bool = False
    reason: str | None = None


class ProbeVerifier:
    """Verify senders by probing their server with a zero-length request.

    A successful probe (status 20) means the sender's server recognises
    the mailbox and returns its certificate fingerprint.  Results are
    cached so each sender is probed at most once.
    """

    def __init__(
        self,
        cache: SenderVerificationCache,
        identity_cert: Path,
        identity_key: Path,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
    ) -> None:
        self.cache = cache
        self.identity_cert = identity_cert
        self.identity_key = identity_key
        self.port = port
        self.timeout = timeout

    async def verify_sender(self, address: MisfinAddress) -> VerificationResult:
        sender_addr = address.address

        # Cache hit
        cached_fp = self.cache.get_fingerprint(sender_addr)
        if cached_fp is not None:
            logger.debug("verification_cache_hit", sender=sender_addr)
            return VerificationResult(
                verified=True,
                fingerprint=cached_fp,
                cached=True,
            )

        # Send zero-length probe
        logger.debug("verification_probe", sender=sender_addr)
        try:
            async with MisfinClient(
                port=self.port,
                timeout=self.timeout,
                trust_on_first_use=False,
                client_cert=self.identity_cert,
                client_key=self.identity_key,
            ) as client:
                request = MisfinRequest(
                    mailbox=address.mailbox,
                    hostname=address.hostname,
                    content_length=0,
                    raw_message=b"",
                )
                response = await client._send_request(request, address.hostname)

            if not is_success(response.status):
                logger.warning(
                    "verification_probe_rejected",
                    sender=sender_addr,
                    status=response.status,
                    meta=response.meta,
                )
                return VerificationResult(
                    verified=False,
                    reason=(f"Probe returned status {response.status}: {response.meta}"),
                )

            raw_fingerprint = response.fingerprint
            if not raw_fingerprint:
                return VerificationResult(
                    verified=False,
                    reason="Probe response missing fingerprint",
                )

            fingerprint = normalize_fingerprint(raw_fingerprint)
            self.cache.add_verified(sender_addr, fingerprint)
            logger.info(
                "verification_probe_success",
                sender=sender_addr,
                fingerprint=fingerprint,
            )
            return VerificationResult(verified=True, fingerprint=fingerprint)

        except TimeoutError:
            logger.warning("verification_probe_timeout", sender=sender_addr)
            return VerificationResult(verified=False, reason="Probe timed out")
        except Exception as e:
            logger.error(
                "verification_probe_error",
                sender=sender_addr,
                error=str(e),
            )
            return VerificationResult(verified=False, reason=f"Probe error: {e}")
