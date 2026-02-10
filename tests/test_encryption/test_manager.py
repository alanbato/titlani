"""Tests for EncryptionManager (X25519 ECDH + AES-256-GCM)."""

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from titlani.encryption.manager import (
    _EPHEMERAL_KEY_SIZE,
    _NONCE_SIZE,
    EncryptionManager,
)


def _generate_keypair(tmp_path, mailbox):
    """Generate X25519 PEM key files and return (private_key_path, public_key_path)."""
    private_key = X25519PrivateKey.generate()

    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path = tmp_path / f"{mailbox}.enc.key"
    pub_path = tmp_path / f"{mailbox}.enc.pub"
    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)

    return priv_path, pub_path


class TestEncryptionManager:
    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_path, _ = _generate_keypair(tmp_path, "alice")

        mgr = EncryptionManager(mailbox_dir)
        mgr.load_key_for_mailbox("alice", priv_path)

        plaintext = b"Hello, Alice!"
        encrypted = mgr.encrypt("alice", plaintext)
        assert encrypted != plaintext
        decrypted = mgr.decrypt("alice", encrypted)
        assert decrypted == plaintext

    def test_wrong_key_fails_to_decrypt(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_a, _ = _generate_keypair(tmp_path, "alice")
        priv_b, _ = _generate_keypair(tmp_path, "bob")

        mgr_a = EncryptionManager(mailbox_dir)
        mgr_a.load_key_for_mailbox("alice", priv_a)

        mgr_b = EncryptionManager(mailbox_dir)
        mgr_b.load_key_for_mailbox("bob", priv_b)

        encrypted = mgr_a.encrypt("alice", b"secret data")

        with pytest.raises(InvalidTag):
            mgr_b.decrypt("bob", encrypted)

    def test_has_key(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_path, _ = _generate_keypair(tmp_path, "alice")

        mgr = EncryptionManager(mailbox_dir)
        assert not mgr.has_key("alice")

        mgr.load_key_for_mailbox("alice", priv_path)
        assert mgr.has_key("alice")

    def test_encrypt_without_key_raises(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        mgr = EncryptionManager(mailbox_dir)

        with pytest.raises(ValueError, match="No encryption key"):
            mgr.encrypt("alice", b"data")

    def test_decrypt_without_key_raises(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        mgr = EncryptionManager(mailbox_dir)

        with pytest.raises(ValueError, match="No private key"):
            mgr.decrypt("alice", b"x" * 100)

    def test_load_public_key_encrypt_only(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_path, pub_path = _generate_keypair(tmp_path, "alice")

        # Load only public key
        mgr = EncryptionManager(mailbox_dir)
        mgr.load_public_key_for_mailbox("alice", pub_path)

        assert mgr.has_key("alice")

        # Encrypt works
        encrypted = mgr.encrypt("alice", b"hello")
        assert len(encrypted) > 0

        # Decrypt raises (no private key)
        with pytest.raises(ValueError, match="No private key"):
            mgr.decrypt("alice", encrypted)

        # Verify decryptable with private key via classmethod
        decrypted = EncryptionManager.decrypt_with_key(priv_path, encrypted)
        assert decrypted == b"hello"

    def test_decrypt_with_key_classmethod(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_path, _ = _generate_keypair(tmp_path, "alice")

        mgr = EncryptionManager(mailbox_dir)
        mgr.load_key_for_mailbox("alice", priv_path)

        plaintext = b"classmethod test"
        encrypted = mgr.encrypt("alice", plaintext)

        decrypted = EncryptionManager.decrypt_with_key(priv_path, encrypted)
        assert decrypted == plaintext

    def test_encrypted_data_format(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_path, _ = _generate_keypair(tmp_path, "alice")

        mgr = EncryptionManager(mailbox_dir)
        mgr.load_key_for_mailbox("alice", priv_path)

        plaintext = b"format test"
        enc1 = mgr.encrypt("alice", plaintext)
        enc2 = mgr.encrypt("alice", plaintext)

        # Minimum size: 32 (ephemeral key) + 12 (nonce) + 16 (GCM tag) = 60
        min_size = _EPHEMERAL_KEY_SIZE + _NONCE_SIZE + 16
        assert len(enc1) >= min_size + len(plaintext)
        assert len(enc2) >= min_size + len(plaintext)

        # Ephemeral keys differ per encryption
        assert enc1[:_EPHEMERAL_KEY_SIZE] != enc2[:_EPHEMERAL_KEY_SIZE]

        # Nonces differ per encryption
        nonce1 = enc1[_EPHEMERAL_KEY_SIZE : _EPHEMERAL_KEY_SIZE + _NONCE_SIZE]
        nonce2 = enc2[_EPHEMERAL_KEY_SIZE : _EPHEMERAL_KEY_SIZE + _NONCE_SIZE]
        assert nonce1 != nonce2

    def test_decrypt_truncated_data_raises(self, tmp_path):
        mailbox_dir = tmp_path / "mailboxes"
        mailbox_dir.mkdir()

        priv_path, _ = _generate_keypair(tmp_path, "alice")

        mgr = EncryptionManager(mailbox_dir)
        mgr.load_key_for_mailbox("alice", priv_path)

        with pytest.raises(ValueError, match="too short"):
            mgr.decrypt("alice", b"short")
