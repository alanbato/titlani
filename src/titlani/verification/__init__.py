"""Sender verification for Misfin(C) protocol.

Probe-based verification confirms that messages originate from servers
that recognize the sender's mailbox.
"""

from .cache import SenderVerificationCache
from .handler import VerifyingHandler
from .verifier import ProbeVerifier, VerificationMode, VerificationResult

__all__ = [
    "ProbeVerifier",
    "SenderVerificationCache",
    "VerificationMode",
    "VerificationResult",
    "VerifyingHandler",
]
