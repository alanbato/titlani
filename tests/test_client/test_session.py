"""Tests for MisfinClient."""

import pytest

from titlani.client.session import MisfinClient


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
