"""Tests for MisfinClient auto-retry on rate limit (status 44)."""

from unittest.mock import AsyncMock, patch

from titlani.client.session import MisfinClient
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode


class TestParseRetryDelay:
    def _client(self, **kwargs):
        return MisfinClient(trust_on_first_use=False, **kwargs)

    def test_parse_delay_from_meta(self):
        delay = self._client()._parse_retry_delay("Slow Down. Retry after 30s")
        assert delay == 30.0

    def test_parse_delay_with_spaces(self):
        delay = self._client()._parse_retry_delay("Retry after 5 s")
        assert delay == 5.0

    def test_parse_delay_unparseable_returns_base_delay(self):
        delay = self._client()._parse_retry_delay("Slow down please")
        assert delay == 1.0

    def test_parse_delay_empty_meta(self):
        delay = self._client()._parse_retry_delay("")
        assert delay == 1.0

    def test_parse_delay_uses_custom_base_delay(self):
        delay = self._client(retry_base_delay=2.5)._parse_retry_delay("Slow down please")
        assert delay == 2.5


class TestRetryOnRateLimit:
    async def test_retry_succeeds_on_second_attempt(self):
        client = MisfinClient(trust_on_first_use=False, max_retries=3)
        slow_response = MisfinResponse(
            status=StatusCode.SLOW_DOWN,
            meta="Slow Down. Retry after 1s",
        )
        success_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            side_effect=[slow_response, success_response],
        ) as mock_send:
            with patch("titlani.client.session.asyncio.sleep"):
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SUCCESS
        assert mock_send.call_count == 2

    async def test_retry_exhausts_max_retries(self):
        client = MisfinClient(trust_on_first_use=False, max_retries=2)
        slow_response = MisfinResponse(
            status=StatusCode.SLOW_DOWN,
            meta="Slow Down. Retry after 1s",
        )

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=slow_response,
        ) as mock_send:
            with patch("titlani.client.session.asyncio.sleep"):
                response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SLOW_DOWN
        # 1 initial + 2 retries = 3
        assert mock_send.call_count == 3

    async def test_non_44_status_returned_immediately(self):
        client = MisfinClient(trust_on_first_use=False, max_retries=3)
        success_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=success_response,
        ) as mock_send:
            response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SUCCESS
        assert mock_send.call_count == 1

    async def test_max_retries_zero_disables_retry(self):
        client = MisfinClient(trust_on_first_use=False, max_retries=0)
        slow_response = MisfinResponse(
            status=StatusCode.SLOW_DOWN,
            meta="Slow Down. Retry after 1s",
        )

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=slow_response,
        ) as mock_send:
            response = await client.send_raw("test@example.com", b"test")

        assert response.status == StatusCode.SLOW_DOWN
        assert mock_send.call_count == 1

    async def test_retry_uses_parsed_delay(self):
        client = MisfinClient(trust_on_first_use=False, max_retries=1)
        slow_response = MisfinResponse(
            status=StatusCode.SLOW_DOWN,
            meta="Slow Down. Retry after 5s",
        )
        success_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            side_effect=[slow_response, success_response],
        ):
            with patch(
                "titlani.client.session.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep:
                await client.send_raw("test@example.com", b"test")

        mock_sleep.assert_called_once_with(5.0)
