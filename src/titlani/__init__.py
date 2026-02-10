"""Titlani - Misfin(B/C) mail protocol client and server library."""

# Protocol
# Client
from .client.session import MisfinClient

# Content
from .content.gemmail import GemmailMessage, MisfinAddress

# Encryption
from .encryption.manager import EncryptionManager

# Identity
from .identity.certificate import (
    MisfinIdentity,
    extract_identity,
    generate_encryption_keypair,
    generate_identity_cert,
    normalize_fingerprint,
)
from .protocol.constants import DEFAULT_PORT
from .protocol.request import MisfinRequest
from .protocol.response import MisfinResponse
from .protocol.status import StatusCode

# Server
from .server.config import ServerConfig
from .server.handler import FileMailboxHandler, MessageHandler
from .server.server import start_server

__all__ = [
    # Protocol
    "DEFAULT_PORT",
    "MisfinRequest",
    "MisfinResponse",
    "StatusCode",
    # Content
    "GemmailMessage",
    "MisfinAddress",
    # Identity
    "MisfinIdentity",
    "extract_identity",
    "generate_encryption_keypair",
    "generate_identity_cert",
    "normalize_fingerprint",
    # Client
    "MisfinClient",
    # Encryption
    "EncryptionManager",
    # Server
    "FileMailboxHandler",
    "MessageHandler",
    "ServerConfig",
    "start_server",
]
