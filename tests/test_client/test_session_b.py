"""Tests for Misfin(B) client-side fallback."""

from unittest.mock import AsyncMock, patch

from titlani.client.session import MisfinClient
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode


class TestMisfinBFallback:
    async def test_fallback_triggered_on_bad_request(self):
        client = MisfinClient(trust_on_first_use=False, misfin_b_fallback=True)
        c_response = MisfinResponse(status=StatusCode.BAD_REQUEST, meta="Bad request")
        b_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=c_response,
        ):
            with patch.object(
                client,
                "_send_request_b",
                new_callable=AsyncMock,
                return_value=b_response,
            ) as mock_b:
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SUCCESS
        mock_b.assert_called_once()

    async def test_fallback_triggered_on_temp_failure(self):
        client = MisfinClient(trust_on_first_use=False, misfin_b_fallback=True)
        c_response = MisfinResponse(
            status=StatusCode.TEMPORARY_FAILURE,
            meta="Temporary failure",
        )
        b_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=c_response,
        ):
            with patch.object(
                client,
                "_send_request_b",
                new_callable=AsyncMock,
                return_value=b_response,
            ) as mock_b:
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SUCCESS
        mock_b.assert_called_once()

    async def test_fallback_triggered_on_cert_required(self):
        client = MisfinClient(trust_on_first_use=False, misfin_b_fallback=True)
        c_response = MisfinResponse(
            status=StatusCode.CERTIFICATE_REQUIRED,
            meta="Certificate required",
        )
        b_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=c_response,
        ):
            with patch.object(
                client,
                "_send_request_b",
                new_callable=AsyncMock,
                return_value=b_response,
            ) as mock_b:
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SUCCESS
        mock_b.assert_called_once()

    async def test_fallback_disabled(self):
        client = MisfinClient(trust_on_first_use=False, misfin_b_fallback=False)
        c_response = MisfinResponse(status=StatusCode.BAD_REQUEST, meta="Bad request")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=c_response,
        ):
            with patch.object(
                client,
                "_send_request_b",
                new_callable=AsyncMock,
            ) as mock_b:
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.BAD_REQUEST
        mock_b.assert_not_called()

    async def test_no_fallback_for_success(self):
        client = MisfinClient(trust_on_first_use=False, misfin_b_fallback=True)
        c_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=c_response,
        ):
            with patch.object(
                client,
                "_send_request_b",
                new_callable=AsyncMock,
            ) as mock_b:
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SUCCESS
        mock_b.assert_not_called()

    async def test_no_double_fallback(self):
        """B request that already failed should not trigger another B."""
        client = MisfinClient(trust_on_first_use=False, misfin_b_fallback=True)
        # Simulate a B-versioned request
        c_response = MisfinResponse(status=StatusCode.BAD_REQUEST, meta="Bad request")

        call_count = 0

        async def mock_send(request, hostname):
            nonlocal call_count
            call_count += 1
            return c_response

        with patch.object(client, "_send_request_once", side_effect=mock_send):
            # Send a B-versioned request directly - should not
            # trigger fallback since protocol_version would be "B"
            from titlani.protocol.request import MisfinRequest

            b_request = MisfinRequest(
                mailbox="test",
                hostname="example.com",
                content_length=4,
                raw_message=b"test",
                protocol_version="B",
            )
            response = await client._send_request(b_request, "example.com")

        # Should not have tried B fallback since request
        # was already B
        assert response.status == StatusCode.BAD_REQUEST
        assert call_count == 1
