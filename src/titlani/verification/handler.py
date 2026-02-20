"""Handler decorator that adds sender verification."""

from tlacacoca import get_logger

from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode
from ..server.handler import MessageHandler
from .combined_verifier import CombinedVerifier
from .spki_verifier import SPKIVerifier
from .verifier import (
    ProbeVerifier,
    VerificationMethod,
    VerificationMode,
    VerificationResult,
)

logger = get_logger(__name__)


class VerifyingHandler(MessageHandler):
    """Wraps a MessageHandler to verify sender addresses before delivery.

    Zero-length messages (verification probes) are always forwarded
    to the wrapped handler without verification to avoid infinite loops.
    """

    def __init__(
        self,
        wrapped: MessageHandler,
        verifier: ProbeVerifier | SPKIVerifier | CombinedVerifier,
        mode: VerificationMode = VerificationMode.OPTIONAL,
        method: VerificationMethod = VerificationMethod.PROBE,
    ) -> None:
        self.wrapped = wrapped
        self.verifier = verifier
        self.mode = mode
        self.method = method

    def _wrap_result(self, result: VerificationResult) -> VerificationResult:
        """Ensure result has a checks dict for sidecar metadata.

        CombinedVerifier already provides checks natively.
        For single-method verifiers, wrap the result in a one-entry dict.
        """
        if result.checks is not None:
            return result

        method_key = self.method.value
        return VerificationResult(
            verified=result.verified,
            fingerprint=result.fingerprint,
            cached=result.cached,
            reason=result.reason,
            checks={method_key: result},
        )

    async def handle_message(self, request: MisfinRequest) -> MisfinResponse:
        if self.mode == VerificationMode.OFF:
            return await self.wrapped.handle_message(request)

        # Don't verify verification probes (prevents infinite loops)
        if request.content_length == 0:
            logger.debug(
                "verification_probe_bypass",
                mailbox=request.mailbox,
            )
            return await self.wrapped.handle_message(request)

        # Parse message to extract sender
        try:
            message = request.parse_message()
        except ValueError:
            # Let the wrapped handler produce the error response
            return await self.wrapped.handle_message(request)

        if not message.senders:
            if self.mode == VerificationMode.REQUIRED:
                logger.warning(
                    "verification_no_sender_required",
                    mailbox=request.mailbox,
                )
                return MisfinResponse(
                    status=StatusCode.UNAUTHORIZED_SENDER,
                    meta="Sender required for verification",
                )
            logger.debug(
                "verification_no_sender_optional",
                mailbox=request.mailbox,
            )
            return await self.wrapped.handle_message(request)

        sender = message.senders[0]
        result = await self.verifier.verify_sender(sender)
        wrapped_result = self._wrap_result(result)

        # Attach verification metadata to the request for sidecar storage
        request.verification_result = wrapped_result

        if result.verified:
            logger.info(
                "sender_verified",
                sender=sender.address,
                fingerprint=(
                    result.fingerprint[:16] + "..." if result.fingerprint else None
                ),
                cached=result.cached,
            )

        if not result.verified:
            if self.mode == VerificationMode.REQUIRED:
                logger.warning(
                    "sender_rejected",
                    sender=sender.address,
                    reason=result.reason,
                )
                return MisfinResponse(
                    status=StatusCode.UNAUTHORIZED_SENDER,
                    meta=(f"Sender verification failed: {result.reason}"),
                )
            logger.info(
                "sender_unverified_allowed",
                sender=sender.address,
                reason=result.reason,
            )

        return await self.wrapped.handle_message(request)
