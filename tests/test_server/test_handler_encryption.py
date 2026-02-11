"""Tests for FileMailboxHandler with encryption."""

from titlani.content.gemmail import GemmailMessage, MisfinAddress
from titlani.encryption.manager import EncryptionManager
from titlani.protocol.request import MisfinRequest
from titlani.protocol.status import StatusCode
from titlani.server.handler import FileMailboxHandler


class TestHandlerEncryption:
    def _make_request(self, mailbox="alice", hostname="example.com"):
        msg = GemmailMessage(
            senders=[MisfinAddress("bob", "other.com")],
            recipients=[MisfinAddress(mailbox, hostname)],
            timestamps=[],
            body="Hello!\n",
        )
        raw = msg.to_bytes()
        return MisfinRequest(
            mailbox=mailbox,
            hostname=hostname,
            content_length=len(raw),
            raw_message=raw,
        )

    async def test_stores_encrypted_with_manager(self, tmp_path):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey,
        )

        mailbox_dir = tmp_path / "mailboxes"
        (mailbox_dir / "alice").mkdir(parents=True)

        private_key = X25519PrivateKey.generate()
        key_path = tmp_path / "alice.enc.key"
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        pub_path = tmp_path / "alice.enc.pub"
        pub_path.write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

        # Server only loads public key (encrypt-only)
        mgr = EncryptionManager(mailbox_dir)
        mgr.load_public_key_for_mailbox("alice", pub_path)

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            encryption_manager=mgr,
        )

        request = self._make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        enc_files = list((mailbox_dir / "alice").glob("*.gemmail.enc.new"))
        assert len(enc_files) == 1

        # User decrypts with private key (separate from server)
        decrypted = EncryptionManager.decrypt_with_key(
            key_path, enc_files[0].read_bytes()
        )
        msg = GemmailMessage.from_bytes(decrypted)
        assert "Hello!" in msg.body

    async def test_stores_plaintext_without_key(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        (mailbox_dir / "alice").mkdir(parents=True)

        # Manager exists but no key loaded for this mailbox
        mgr = EncryptionManager(mailbox_dir)

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
            encryption_manager=mgr,
        )

        request = self._make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        plain_files = list((mailbox_dir / "alice").glob("*.gemmail.new"))
        assert len(plain_files) == 1
        assert b"Hello!" in plain_files[0].read_bytes()

    async def test_stores_plaintext_without_manager(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        (mailbox_dir / "alice").mkdir(parents=True)

        handler = FileMailboxHandler(
            mailbox_dir=mailbox_dir,
            hostname="example.com",
        )

        request = self._make_request()
        response = await handler.handle_message(request)

        assert response.status == StatusCode.SUCCESS

        plain_files = list((mailbox_dir / "alice").glob("*.gemmail.new"))
        assert len(plain_files) == 1
