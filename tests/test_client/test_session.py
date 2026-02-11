"""Tests for MisfinClient."""

from unittest.mock import AsyncMock, patch

import pytest

from titlani.client.session import MisfinClient
from titlani.protocol.response import MisfinResponse
from titlani.protocol.status import StatusCode


class TestMisfinClient:
    def test_init_defaults(self):
        client = MisfinClient(trust_on_first_use=False)
        assert client.timeout == 30.0
        assert client.tofu_db is None

    def test_init_with_tofu(self, tmp_path):
        db_path = tmp_path / "tofu.db"
        client = MisfinClient(tofu_db_path=db_path)
        assert client.tofu_db is not None

    def test_init_cert_without_key_raises(self, test_identity_cert):
        cert_path, _ = test_identity_cert
        with pytest.raises(ValueError, match="client_key is required"):
            MisfinClient(
                client_cert=cert_path,
                trust_on_first_use=False,
            )

    def test_init_key_without_cert_raises(self, test_identity_cert):
        _, key_path = test_identity_cert
        with pytest.raises(ValueError, match="client_cert is required"):
            MisfinClient(
                client_key=key_path,
                trust_on_first_use=False,
            )

    async def test_context_manager(self):
        async with MisfinClient(trust_on_first_use=False) as client:
            assert isinstance(client, MisfinClient)

    async def test_send_invalid_address(self):
        async with MisfinClient(trust_on_first_use=False) as client:
            with pytest.raises(ValueError, match="Invalid address"):
                await client.send("no-at-sign", "hello")


class TestContextManager:
    async def test_aexit_closes_tofu_db(self, tmp_path):
        db_path = tmp_path / "tofu.db"
        client = MisfinClient(tofu_db_path=db_path)
        assert client.tofu_db is not None

        async with client:
            pass

        assert client.tofu_db is None

    async def test_aexit_without_tofu_is_noop(self):
        client = MisfinClient(trust_on_first_use=False)
        async with client:
            pass
        assert client.tofu_db is None


class TestRedirectLimit:
    async def test_redirect_limit_exceeded(self):
        client = MisfinClient(trust_on_first_use=False)
        redirect_response = MisfinResponse(
            status=StatusCode.REDIRECT_PERMANENT,
            meta="other@example.com",
        )

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            return_value=redirect_response,
        ):
            response = await client.send_raw("test@example.com", b"hello")

        assert response.status == StatusCode.PERMANENT_FAILURE
        assert "Too many redirects" in response.meta

    async def test_redirect_within_limit_follows(self):
        client = MisfinClient(trust_on_first_use=False)
        redirect_response = MisfinResponse(
            status=StatusCode.REDIRECT_TEMPORARY,
            meta="other@example.com",
        )
        success_response = MisfinResponse(status=StatusCode.SUCCESS, meta="delivered")

        with patch.object(
            client,
            "_send_request_once",
            new_callable=AsyncMock,
            side_effect=[redirect_response, success_response],
        ):
            response = await client.send_raw("test@example.com", b"hello")

        assert response.status == StatusCode.SUCCESS
