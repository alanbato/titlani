# At-Rest Encryption

Titlani can encrypt stored messages so that only the mailbox owner can read them. The server encrypts incoming mail using the recipient's public key, and only the corresponding private key (held by the user) can decrypt it.

## Generate Encryption Keys

Each mailbox needs an X25519 keypair. Generate one alongside an identity certificate:

```bash
titlani identity generate alice example.com \
    --with-encryption-key --output-dir ./keys
```

This creates four files:

| File | Purpose | Permissions |
|------|---------|-------------|
| `alice.pem` | Identity certificate | 644 |
| `alice.key` | Identity private key | 600 |
| `alice.enc.pub` | Encryption public key | 644 |
| `alice.enc.key` | Encryption private key | 600 |

You can also generate encryption keys programmatically:

```python
from titlani import generate_encryption_keypair

public_pem, private_pem = generate_encryption_keypair()
```

## Enable in Config

Add an `[encryption]` section to your TOML config:

```toml
[encryption]
enable = true
```

The server scans for `<mailbox>.enc.pub` files in the mailbox directory by default. To store public keys in a separate directory:

```toml
[encryption]
enable = true
key_dir = "/etc/titlani/keys"
```

## Deploy Public Keys

Copy each mailbox's `.enc.pub` file where the server can find it:

```bash
# Default: alongside the mailbox directories
cp alice.enc.pub /var/lib/titlani/mailboxes/

# Or in a dedicated key directory (matching key_dir config)
cp alice.enc.pub /etc/titlani/keys/
```

The server only needs the **public key**. It never touches private keys.

## Multi-User Deployment

On a multi-user Unix system, the security model separates the server's encrypt-only access from each user's decrypt access:

```
Server process (titlani user)          Each Unix user
─────────────────────────────          ──────────────
Reads: alice.enc.pub (644)             Reads: alice.enc.key (600, user-owned)
       bob.enc.pub   (644)                    bob.enc.key   (600, user-owned)

Can: encrypt incoming mail             Can: decrypt their own mail
Cannot: decrypt any stored mail        Cannot: decrypt other users' mail
```

Set up the key directory:

```bash
# Public keys readable by server
sudo mkdir -p /etc/titlani/keys
sudo cp alice.enc.pub bob.enc.pub /etc/titlani/keys/
sudo chmod 644 /etc/titlani/keys/*.enc.pub

# Private keys owned by each user
cp alice.enc.key ~alice/.titlani/
chmod 600 ~alice/.titlani/alice.enc.key
chown alice:alice ~alice/.titlani/alice.enc.key
```

!!! warning
    A compromised server process can read *future* incoming messages in plaintext (before encryption) — at-rest encryption protects stored messages on disk, not messages in transit through the server.

## Reading Encrypted Mail

Encrypted messages are stored as `.gemmail.enc` files. The CLI decrypts them using the private key:

```bash
# Auto-discovers <mailbox>.enc.key from the mailbox parent directory
titlani mail read mailboxes/alice/2025-01-15T10-30-00.gemmail.enc

# Or specify the key explicitly
titlani mail read message.gemmail.enc --encryption-key ~/.titlani/alice.enc.key
```

The `mail reply` command works the same way:

```bash
titlani mail reply message.gemmail.enc \
    --encryption-key ~/.titlani/alice.enc.key \
    --cert alice.pem --key alice.key \
    --message "Got it, thanks!"
```

## How It Works

Titlani uses an ECIES-like scheme: X25519 ECDH key agreement, HKDF-SHA256 key derivation, and AES-256-GCM authenticated encryption.

**Encryption (server, on message receipt):**

1. Generate an ephemeral X25519 keypair
2. Perform ECDH between the ephemeral private key and the mailbox's public key
3. Derive a 256-bit symmetric key via HKDF-SHA256 (info: `titlani-mailbox-encryption`)
4. Encrypt the message with AES-256-GCM using a random 12-byte nonce
5. Write: `[32B ephemeral pubkey][12B nonce][ciphertext + 16B GCM tag]`

**Decryption (user, via CLI):**

1. Read the ephemeral public key from the first 32 bytes
2. Perform ECDH between the mailbox's private key and the ephemeral public key
3. Derive the same symmetric key via HKDF-SHA256
4. Decrypt and verify the AES-256-GCM ciphertext

Each message uses a unique ephemeral keypair and nonce, so identical plaintext produces different ciphertext.

## Mailboxes Without Keys

If a mailbox has no `.enc.pub` file, messages are stored as plaintext `.gemmail` files. Encryption is per-mailbox — you can encrypt some mailboxes and leave others in plaintext.

## Programmatic Usage

```python
from pathlib import Path
from titlani import EncryptionManager

# Server-side: encrypt-only with public key
manager = EncryptionManager(Path("mailboxes"))
manager.load_public_key_for_mailbox("alice", Path("keys/alice.enc.pub"))
encrypted = manager.encrypt("alice", message_bytes)

# User-side: decrypt with private key
plaintext = EncryptionManager.decrypt_with_key(
    Path("alice.enc.key"), encrypted
)
```

## Full Example

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
mailbox_dir = "/var/lib/titlani/mailboxes"
identity_certfile = "/etc/titlani/identity.pem"
identity_keyfile = "/etc/titlani/identity.key"

[encryption]
enable = true
key_dir = "/etc/titlani/keys"

[rate_limit]
enable = true
capacity = 10
```
