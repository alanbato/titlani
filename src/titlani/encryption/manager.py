"""Encryption manager for per-mailbox at-rest encryption.

Uses X25519 ECDH + HKDF-SHA256 + AES-256-GCM (ECIES-like scheme).
Each mailbox has a long-term X25519 keypair. Encryption generates an
ephemeral X25519 keypair, performs ECDH, derives a symmetric key via
HKDF, and encrypts with AES-256-GCM.

Wire format: [32B ephemeral pubkey][12B nonce][ciphertext + 16B GCM tag]
"""

import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from tlacacoca import get_logger

logger = get_logger(__name__)

_HKDF_INFO = b"titlani-mailbox-encryption"
_NONCE_SIZE = 12
_EPHEMERAL_KEY_SIZE = 32
_MIN_TOKEN_SIZE = _EPHEMERAL_KEY_SIZE + _NONCE_SIZE + 16  # + GCM tag


def _derive_symmetric_key(shared_secret: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(shared_secret)


def _decrypt_with_private_key(private_key: X25519PrivateKey, token: bytes) -> bytes:
    if len(token) < _MIN_TOKEN_SIZE:
        raise ValueError(
            f"Encrypted data too short: {len(token)} bytes, minimum {_MIN_TOKEN_SIZE}"
        )

    ephemeral_pub_bytes = token[:_EPHEMERAL_KEY_SIZE]
    nonce = token[_EPHEMERAL_KEY_SIZE : _EPHEMERAL_KEY_SIZE + _NONCE_SIZE]
    ciphertext = token[_EPHEMERAL_KEY_SIZE + _NONCE_SIZE :]

    ephemeral_pub = X25519PublicKey.from_public_bytes(ephemeral_pub_bytes)
    shared_secret = private_key.exchange(ephemeral_pub)
    symmetric_key = _derive_symmetric_key(shared_secret)

    return AESGCM(symmetric_key).decrypt(nonce, ciphertext, None)


class EncryptionManager:
    """Manages per-mailbox encryption using X25519 ECDH + AES-256-GCM."""

    def __init__(self, mailbox_dir: Path) -> None:
        self.mailbox_dir = mailbox_dir
        self._private_keys: dict[str, X25519PrivateKey] = {}
        self._public_keys: dict[str, X25519PublicKey] = {}

    def load_key_for_mailbox(self, mailbox: str, private_key_path: Path) -> None:
        pem_data = private_key_path.read_bytes()
        private_key = serialization.load_pem_private_key(pem_data, password=None)
        if not isinstance(private_key, X25519PrivateKey):
            raise TypeError(f"Expected X25519 private key, got {type(private_key)}")
        self._private_keys[mailbox] = private_key
        self._public_keys[mailbox] = private_key.public_key()

    def load_public_key_for_mailbox(self, mailbox: str, public_key_path: Path) -> None:
        pem_data = public_key_path.read_bytes()
        public_key = serialization.load_pem_public_key(pem_data)
        if not isinstance(public_key, X25519PublicKey):
            raise TypeError(f"Expected X25519 public key, got {type(public_key)}")
        self._public_keys[mailbox] = public_key

    def has_key(self, mailbox: str) -> bool:
        return mailbox in self._public_keys

    def encrypt(self, mailbox: str, data: bytes) -> bytes:
        if mailbox not in self._public_keys:
            raise ValueError(f"No encryption key loaded for mailbox: {mailbox}")
        logger.debug("encryption_encrypt", mailbox=mailbox)

        recipient_pub = self._public_keys[mailbox]

        ephemeral_priv = X25519PrivateKey.generate()
        ephemeral_pub_bytes = ephemeral_priv.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

        shared_secret = ephemeral_priv.exchange(recipient_pub)
        symmetric_key = _derive_symmetric_key(shared_secret)

        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = AESGCM(symmetric_key).encrypt(nonce, data, None)

        return ephemeral_pub_bytes + nonce + ciphertext

    def decrypt(self, mailbox: str, token: bytes) -> bytes:
        if mailbox not in self._private_keys:
            logger.error(
                "encryption_missing_private_key",
                mailbox=mailbox,
            )
            raise ValueError(f"No private key loaded for mailbox: {mailbox}")
        logger.debug("encryption_decrypt", mailbox=mailbox)
        return _decrypt_with_private_key(self._private_keys[mailbox], token)

    @classmethod
    def decrypt_with_key(cls, private_key_path: Path, token: bytes) -> bytes:
        if not private_key_path.exists():
            logger.error(
                "encryption_missing_key_file",
                path=str(private_key_path),
            )
        pem_data = private_key_path.read_bytes()
        private_key = serialization.load_pem_private_key(pem_data, password=None)
        if not isinstance(private_key, X25519PrivateKey):
            raise TypeError(f"Expected X25519 private key, got {type(private_key)}")
        return _decrypt_with_private_key(private_key, token)
