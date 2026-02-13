"""Handler decorator that adds sender verification."""

from tlacacoca import get_logger

from ..protocol.request import MisfinRequest
from ..protocol.response import MisfinResponse
from ..protocol.status import StatusCode
from ..server.handler import MessageHandler
from .spki_verifier import SPKIVerifier
from .verifier import ProbeVerifier, VerificationMode

logger = get_logger(__name__)


class VerifyingHandler(MessageHandler):
    """Wraps a MessageHandler to verify sender addresses before delivery.

    Zero-length messages (verification probes) are always forwarded
    to the wrapped handler without verification to avoid infinite loops.
    """

    def __init__(
        self,
        wrapped: MessageHandler,
        verifier: ProbeVerifier | SPKIVerifier,
        mode: VerificationMode = VerificationMode.OPTIONAL,
    ) -> None:
        self.wrapped = wrapped
        self.verifier = verifier
        self.mode = mode

    async def handle_message(self, request: MisfinRequest) -> MisfinResponse:
        if self.mode == VerificationMode.OFF:
            return await self.wrapped.handle_message(request)

        # Don't verify verification probes (prevents infinite loops)
        if request.content_length == 0:
            return await self.wrapped.handle_message(request)

        # Parse message to extract sender
        try:
            message = request.parse_message()
        except ValueError:
            # Let the wrapped handler produce the error response
            return await self.wrapped.handle_message(request)

        if not message.senders:
            if self.mode == VerificationMode.REQUIRED:
                return MisfinResponse(
                    status=StatusCode.UNAUTHORIZED_SENDER,
                    meta="Sender required for verification",
                )
            return await self.wrapped.handle_message(request)

        sender = message.senders[0]
        result = await self.verifier.verify_sender(sender)

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
