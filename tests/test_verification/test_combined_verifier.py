"""Tests for CombinedVerifier."""

from unittest.mock import AsyncMock

from titlani.content.gemmail import MisfinAddress
from titlani.verification.combined_verifier import CombinedVerifier
from titlani.verification.verifier import VerificationResult


def _make_address() -> MisfinAddress:
    return MisfinAddress(mailbox="alice", hostname="example.com")


class TestCombinedVerifier:
    async def test_both_pass(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="probe_fp"
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="spki_fp"
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.verified is True
        assert result.fingerprint == "probe_fp"
        assert result.reason is None
        assert result.checks is not None
        assert result.checks["probe"].verified is True
        assert result.checks["spki"].verified is True

    async def test_probe_fails(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=False, reason="timeout"
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="spki_fp"
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.verified is False
        assert "probe: timeout" in result.reason
        assert result.checks["probe"].verified is False
        assert result.checks["spki"].verified is True

    async def test_spki_fails(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="probe_fp"
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=False, reason="SPKI changed"
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.verified is False
        assert "spki: SPKI changed" in result.reason
        assert result.checks["probe"].verified is True
        assert result.checks["spki"].verified is False

    async def test_both_fail(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=False, reason="timeout"
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=False, reason="connection error"
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.verified is False
        assert "probe: timeout" in result.reason
        assert "spki: connection error" in result.reason

    async def test_cached_flag(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="fp1", cached=True
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="fp2", cached=True
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.cached is True

    async def test_cached_false_when_one_not_cached(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="fp1", cached=True
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="fp2", cached=False
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.cached is False

    async def test_fingerprint_falls_back_to_spki(self) -> None:
        probe = AsyncMock()
        probe.verify_sender.return_value = VerificationResult(
            verified=False, reason="timeout"
        )
        spki = AsyncMock()
        spki.verify_sender.return_value = VerificationResult(
            verified=True, fingerprint="spki_fp"
        )

        verifier = CombinedVerifier(probe_verifier=probe, spki_verifier=spki)
        result = await verifier.verify_sender(_make_address())

        assert result.fingerprint == "spki_fp"
