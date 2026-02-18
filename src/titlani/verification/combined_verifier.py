"""Combined probe+spki sender verification."""

import asyncio

from tlacacoca import get_logger

from ..content.gemmail import MisfinAddress
from .spki_verifier import SPKIVerifier
from .verifier import ProbeVerifier, VerificationResult

logger = get_logger(__name__)


class CombinedVerifier:
    """Run both probe and SPKI verification concurrently.

    Overall result is verified only if **both** checks pass.
    Individual sub-results are stored in the ``checks`` dict.
    """

    def __init__(
        self,
        probe_verifier: ProbeVerifier,
        spki_verifier: SPKIVerifier,
    ) -> None:
        self.probe_verifier = probe_verifier
        self.spki_verifier = spki_verifier

    async def verify_sender(self, address: MisfinAddress) -> VerificationResult:
        probe_result, spki_result = await asyncio.gather(
            self.probe_verifier.verify_sender(address),
            self.spki_verifier.verify_sender(address),
        )

        verified = probe_result.verified and spki_result.verified
        checks = {
            "probe": probe_result,
            "spki": spki_result,
        }

        # Use probe fingerprint when available, fall back to spki
        fingerprint = probe_result.fingerprint or spki_result.fingerprint

        if not verified:
            reasons = []
            if not probe_result.verified:
                reasons.append(f"probe: {probe_result.reason}")
            if not spki_result.verified:
                reasons.append(f"spki: {spki_result.reason}")
            reason = "; ".join(reasons)
        else:
            reason = None

        return VerificationResult(
            verified=verified,
            fingerprint=fingerprint,
            cached=probe_result.cached and spki_result.cached,
            reason=reason,
            checks=checks,
        )
