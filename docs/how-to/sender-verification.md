# Sender Verification

The Titlani server can verify that incoming messages originate from legitimate senders. Two verification methods are available:

- **Probe-based** (default): sends a zero-length message to the sender's address and checks whether the sender's server responds with a valid fingerprint.
- **SPKI-based**: connects to the sender's server via TLS, extracts the Subject Public Key Info (SPKI) hash from its certificate, and caches it using a TOFU model. Cryptographically stronger than probe-based verification.

## Enable in Config

Add a `[verification]` section to your TOML config:

```toml
[verification]
mode = "optional"
method = "probe"  # or "spki"
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `"off"` | Verification mode: `"off"`, `"optional"`, or `"required"` |
| `method` | string | `"probe"` | Verification method: `"probe"` or `"spki"` |
| `cache_path` | string | — | Path to SQLite cache file (defaults to `<mailbox_dir>/verification_cache.db`) |
| `cache_ttl` | int | `604800` | Cache time-to-live in seconds (7 days) |
| `probe_timeout` | float | `10.0` | Timeout in seconds for verification probes and SPKI connections |
| `spki_on_change` | string | `"reject"` | Action when a server's SPKI changes: `"reject"` or `"accept"` |

## Modes

### Off (Default)

No verification is performed. Messages are accepted without checking the sender.

```toml
[verification]
mode = "off"
```

### Optional

The server probes the sender's server to verify the mailbox exists. If verification fails (timeout, connection error, or unknown mailbox), the message is **still delivered** but a warning is logged.

```toml
[verification]
mode = "optional"
```

Use this mode to monitor verification results before enforcing.

### Required

Same as optional, but unverified messages are **rejected** with status **61** (unauthorized sender). Messages without a sender in the metadata are also rejected.

```toml
[verification]
mode = "required"
```

## How It Works

When a message arrives from an unknown sender:

1. The server parses the gemmail metadata to extract the first sender address (e.g., `alice@example.com`)
2. The server sends a zero-length verification probe to `alice@example.com`
3. The sender's server receives the probe and responds with status **20** and its identity certificate fingerprint
4. If the probe succeeds, the sender is marked as verified and cached
5. Subsequent messages from the same sender skip the probe (cache hit)

```
Sender's Client                Receiving Server              Sender's Server
     |                               |                            |
     |-- gemmail (alice@sender.com)->|                            |
     |                               |-- probe (content_length=0)->|
     |                               |<-- 20 <fingerprint> -------|
     |                               |                            |
     |                               | (sender verified, cached)  |
     |<-- 20 <fingerprint> ----------|                            |
```

### Verification Probes

A verification probe is a zero-length Misfin request (`content_length=0`). When a Titlani server receives a zero-length request, it responds with:

- Status **20** (success) with the server's identity certificate fingerprint in the meta field
- Standard error codes if the hostname doesn't match (53) or other errors occur

Zero-length messages are never stored — they exist purely for the verification handshake.

## Verification Cache

Verified senders are cached in a SQLite database to avoid repeated probes. The cache stores:

- Sender address (`mailbox@hostname`)
- Certificate fingerprint returned by the probe
- Timestamp of verification

By default the cache file is created at `<mailbox_dir>/verification_cache.db`. Override with:

```toml
[verification]
mode = "required"
cache_path = "/var/lib/titlani/verification.db"
```

!!! tip
    To re-verify a sender (e.g., after their certificate changes), delete the cache file or remove the entry programmatically using `SenderVerificationCache.revoke()`.

## Programmatic Usage

You can use the verification components directly in custom setups:

```python
from titlani.server.handler import FileMailboxHandler
from titlani.verification import (
    ProbeVerifier,
    SenderVerificationCache,
    VerificationMode,
    VerifyingHandler,
)

# Create base handler
base_handler = FileMailboxHandler(
    mailbox_dir=Path("mailboxes"),
    hostname="example.com",
    identity_cert_fingerprint="abc123...",
)

# Create verification cache and verifier
cache = SenderVerificationCache(Path("verification.db"))
verifier = ProbeVerifier(
    cache=cache,
    identity_cert=Path("identity.pem"),
    identity_key=Path("identity.key"),
)

# Wrap the handler
handler = VerifyingHandler(
    wrapped=base_handler,
    verifier=verifier,
    mode=VerificationMode.REQUIRED,
)
```

## SPKI-Based Verification

SPKI verification uses a TOFU (Trust On First Use) model for server identity at the TLS certificate level. This is cryptographically stronger than probe-based verification — it verifies the server's public key rather than just confirming a mailbox exists.

### How It Works

1. On first contact with a server, Titlani connects via TLS and extracts the SHA-256 hash of the server certificate's Subject Public Key Info (SPKI)
2. The hash is cached in SQLite (same database as probe verification)
3. While the cache entry is valid (within `cache_ttl`), subsequent messages from that server are verified without a network call
4. When the entry expires, the server is re-checked and its current SPKI compared against the last known value
5. If the SPKI has changed, behavior depends on `spki_on_change`:
   - `"reject"` (default): reject the message — the operator should investigate
   - `"accept"`: accept the new key and update the cache (less secure, but handles key rotation)

### Enable SPKI Verification

```toml
[verification]
mode = "required"
method = "spki"
spki_on_change = "reject"
```

### Programmatic Usage

```python
from titlani.verification import (
    SPKIVerifier,
    SenderVerificationCache,
    VerificationMode,
    VerifyingHandler,
)

cache = SenderVerificationCache(Path("verification.db"))
verifier = SPKIVerifier(
    cache=cache,
    port=1958,
    timeout=10.0,
    on_spki_change="reject",
)

handler = VerifyingHandler(
    wrapped=base_handler,
    verifier=verifier,
    mode=VerificationMode.REQUIRED,
)
```

## What Verification Proves

**Probe-based** verification confirms that:

- The sender's hostname has a running Misfin server
- The claimed mailbox exists on that server
- The server responds to probes with a fingerprint

**SPKI-based** verification confirms that:

- The sender's server presents the same TLS certificate public key as when first seen
- The server identity has not changed (TOFU model)

Neither method proves that the connecting client is the owner of that mailbox. For that, TLS client certificate verification would be needed (see [Security Model](../explanation/security-model.md#sender-verification)).

## Full Examples

### Probe-based (default)

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
identity_certfile = "identity.pem"
identity_keyfile = "identity.key"
mailbox_dir = "/var/mail/misfin"

[verification]
mode = "required"
probe_timeout = 5.0

[rate_limit]
enable = true
capacity = 10
```

### SPKI-based

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
certfile = "server.pem"
keyfile = "server.key"
mailbox_dir = "/var/mail/misfin"

[verification]
mode = "required"
method = "spki"
cache_ttl = 604800
spki_on_change = "reject"

[rate_limit]
enable = true
capacity = 10
```
