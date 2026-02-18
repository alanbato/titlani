"""Sender verification for Misfin(C) protocol.

Probe-based verification confirms that messages originate from servers
that recognize the sender's mailbox.  SPKI-based verification uses TOFU
on the server's TLS certificate public key.  Combined verification runs
both checks concurrently.
"""

from .cache import SenderVerificationCache
from .combined_verifier import CombinedVerifier
from .handler import VerifyingHandler
from .spki_verifier import SPKIVerifier
from .verifier import (
    ProbeVerifier,
    VerificationMethod,
    VerificationMode,
    VerificationResult,
)

__all__ = [
    "CombinedVerifier",
    "ProbeVerifier",
    "SPKIVerifier",
    "SenderVerificationCache",
    "VerificationMethod",
    "VerificationMode",
    "VerificationResult",
    "VerifyingHandler",
]
