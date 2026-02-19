"""Tests for FileMailboxHandler with encryption."""

from titlani.content.gemmail import GemmailMessage
from titlani.encryption.manager import EncryptionManager
from titlani.protocol.status import StatusCode


class TestHandlerEncryption:
    async def test_stores_encrypted_with_manager(
        self,
        tmp_path,
        mailbox_dir,
        file_mailbox_handler,
        make_misfin_request,
        generate_x25519_keypair,
    ):
        (mailbox_dir / "alice").mkdir()

        priv_path, pub_path = generate_x25519_keypair(tmp_path, "alice")

        # Server only loads public key (encrypt-only)
        mgr = EncryptionManager(mailbox_dir)
        mgr.load_public_key_for_mailbox("alice", pub_path)

        handler = file_mailbox_handler(encryption_manager=mgr)
        request = make_misfin_request(mailbox="alice")
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        enc_files = list((mailbox_dir / "alice").glob("*.gemmail.enc.new"))
        assert len(enc_files) == 1

        # User decrypts with private key (separate from server)
        decrypted = EncryptionManager.decrypt_with_key(
            priv_path, enc_files[0].read_bytes()
        )
        msg = GemmailMessage.from_bytes(decrypted)
        assert "Hello!" in msg.body

    async def test_stores_plaintext_without_key(
        self, mailbox_dir, file_mailbox_handler, make_misfin_request
    ):
        (mailbox_dir / "alice").mkdir()

        # Manager exists but no key loaded for this mailbox
        mgr = EncryptionManager(mailbox_dir)

        handler = file_mailbox_handler(encryption_manager=mgr)
        request = make_misfin_request(mailbox="alice")
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        plain_files = list((mailbox_dir / "alice").glob("*.gemmail.new"))
        assert len(plain_files) == 1
        assert b"Hello!" in plain_files[0].read_bytes()

    async def test_stores_plaintext_without_manager(
        self, mailbox_dir, file_mailbox_handler, make_misfin_request
    ):
        (mailbox_dir / "alice").mkdir()

        handler = file_mailbox_handler()
        request = make_misfin_request(mailbox="alice")
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        plain_files = list((mailbox_dir / "alice").glob("*.gemmail.new"))
        assert len(plain_files) == 1
