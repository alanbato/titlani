"""Tests for VerifyingHandler."""

from unittest.mock import AsyncMock

import pytest

from titlani.protocol.request import MisfinRequest
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode
from titlani.verification.handler import VerifyingHandler
from titlani.verification.verifier import (
    ProbeVerifier,
    VerificationMethod,
    VerificationMode,
    VerificationResult,
)


@pytest.fixture
def wrapped_handler() -> AsyncMock:
    handler = AsyncMock()
    handler.handle_message.return_value = MisfinResponse(
        status=StatusCode.SUCCESS, meta="ok"
    )
    return handler


@pytest.fixture
def mock_verifier() -> AsyncMock:
    return AsyncMock(spec=ProbeVerifier)


def _make_request(content_length: int = 100, raw_message: bytes = b"") -> MisfinRequest:
    if content_length > 0 and not raw_message:
        # Build a minimal valid gemmail
        raw_message = (
            b"sender@example.com Sender\n"
            b"recipient@test.com\n"
            b"2024-01-15T10:30:00Z\n"
            b"Hello\n"
        )
        content_length = len(raw_message)
    return MisfinRequest(
        mailbox="test",
        hostname="test.com",
        content_length=content_length,
        raw_message=raw_message,
    )


class TestVerifyingHandlerOff:
    async def test_mode_off_skips_verification(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OFF,
        )
        request = _make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        mock_verifier.verify_sender.assert_not_called()


class TestVerifyingHandlerProbeBypass:
    async def test_zero_length_skips_verification(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.REQUIRED,
        )
        request = _make_request(content_length=0)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        mock_verifier.verify_sender.assert_not_called()


class TestVerifyingHandlerOptional:
    async def test_verified_sender_passes(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="abc123"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OPTIONAL,
        )
        request = _make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

    async def test_unverified_sender_still_passes(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=False, reason="timeout"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OPTIONAL,
        )
        request = _make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

    async def test_no_senders_passes(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OPTIONAL,
        )
        # Message with empty senders line
        raw = b"\nrecipient@test.com\n2024-01-15T10:30:00Z\nHello\n"
        request = _make_request(content_length=len(raw), raw_message=raw)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS
        mock_verifier.verify_sender.assert_not_called()


class TestVerifyingHandlerRequired:
    async def test_verified_sender_passes(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="abc123"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.REQUIRED,
        )
        request = _make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

    async def test_unverified_sender_rejected(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=False, reason="timeout"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.REQUIRED,
        )
        request = _make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.UNAUTHORIZED_SENDER

    async def test_no_senders_rejected(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.REQUIRED,
        )
        raw = b"\nrecipient@test.com\n2024-01-15T10:30:00Z\nHello\n"
        request = _make_request(content_length=len(raw), raw_message=raw)
        response = await handler.handle_message(request)

        assert response.status == StatusCode.UNAUTHORIZED_SENDER
        mock_verifier.verify_sender.assert_not_called()

    async def test_invalid_message_forwarded(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        """Invalid messages are passed to wrapped handler for its error."""
        wrapped_handler.handle_message.return_value = MisfinResponse(
            status=StatusCode.BAD_REQUEST, meta="Invalid"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.REQUIRED,
        )
        request = _make_request(content_length=3, raw_message=b"bad")
        response = await handler.handle_message(request)

        # The VerifyingHandler catches the parse error and returns BAD_REQUEST
        assert response.status == StatusCode.BAD_REQUEST


class TestVerificationResultOnRequest:
    async def test_result_attached_to_request(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        """Verification result is set on the request before forwarding."""
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="abc123"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OPTIONAL,
            method=VerificationMethod.PROBE,
        )
        request = _make_request()
        await handler.handle_message(request)

        assert request.verification_result is not None
        assert request.verification_result.verified is True
        assert request.verification_result.checks is not None
        assert "probe" in request.verification_result.checks

    async def test_wrap_result_single_method(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        """Single-method result gets wrapped with checks dict."""
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="fp1"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OPTIONAL,
            method=VerificationMethod.SPKI,
        )
        request = _make_request()
        await handler.handle_message(request)

        vr = request.verification_result
        assert vr.checks is not None
        assert "spki" in vr.checks
        assert vr.checks["spki"].verified is True

    async def test_combined_result_not_double_wrapped(
        self, wrapped_handler: AsyncMock
    ) -> None:
        """CombinedVerifier results with existing checks are not re-wrapped."""
        inner_checks = {
            "probe": VerificationResult(verified=True, fingerprint="fp1"),
            "spki": VerificationResult(verified=True, fingerprint="fp2"),
        }
        combined_result = VerificationResult(
            verified=True,
            fingerprint="fp1",
            checks=inner_checks,
        )
        mock_combined = AsyncMock()
        mock_combined.verify_sender.return_value = combined_result

        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_combined,
            mode=VerificationMode.OPTIONAL,
            method=VerificationMethod.PROBE_SPKI,
        )
        request = _make_request()
        await handler.handle_message(request)

        vr = request.verification_result
        assert vr.checks is inner_checks

    async def test_no_result_when_mode_off(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OFF,
        )
        request = _make_request()
        await handler.handle_message(request)

        assert request.verification_result is None

    async def test_failed_result_attached_in_optional_mode(
        self, wrapped_handler: AsyncMock, mock_verifier: AsyncMock
    ) -> None:
        mock_verifier.verify_sender.return_value = VerificationResult(
            verified=False, reason="timeout"
        )
        handler = VerifyingHandler(
            wrapped=wrapped_handler,
            verifier=mock_verifier,
            mode=VerificationMode.OPTIONAL,
            method=VerificationMethod.PROBE,
        )
        request = _make_request()
        await handler.handle_message(request)

        assert request.verification_result is not None
        assert request.verification_result.verified is False
