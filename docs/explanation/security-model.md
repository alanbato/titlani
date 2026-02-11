# Security Model

Titlani's security is built on mandatory TLS, self-signed identity certificates, and Trust-On-First-Use (TOFU) validation.

## Mandatory TLS

All Misfin connections use TLS. There is no plaintext mode. Both client and server must present certificates:

- **Server certificate** — Authenticates the server to the client
- **Client certificate** — Identifies the sender to the server

Certificates are self-signed. There is no Certificate Authority (CA) hierarchy. Trust is established through TOFU, similar to SSH's `known_hosts`.

### TLS and Self-Signed Client Certificates

This is a [known challenge in the Misfin protocol](https://misfin.org/): TLS libraries are not designed for the pattern of requesting non-mandatory, self-signed client certificates without a CA trust chain.

Specifically, OpenSSL 3.x changed the behavior of `CERT_OPTIONAL` (the TLS mode that requests a client certificate without requiring one). In older OpenSSL versions, if a client presented a self-signed cert that couldn't be verified against any CA, the handshake continued and the cert was still accessible. In OpenSSL 3.x, this causes a **silent TLS handshake failure** — the connection is dropped with no error message.

Python's `ssl` module does not expose a custom verify callback, so there is no way to say "request the certificate but skip chain verification" using the standard library.

**Titlani's workaround:** The server does not request client certificates at the TLS level. Instead, sender identity is carried in the gemmail message metadata (the sender line), which the client populates from its identity certificate before sending. This means:

- The server **cannot** cryptographically verify the sender's identity at the transport layer
- Sender information in the gemmail metadata is **self-reported** by the client
- The server **can** still verify the server-to-client direction via TOFU

This is a protocol-level limitation shared by Misfin implementations on modern TLS stacks, not specific to Titlani. Titlani offers optional [at-rest encryption](#at-rest-encryption) to protect stored messages on disk.

## Identity Certificates

Misfin identity certificates use a custom layout:

| Certificate Field | Misfin Usage |
|-------------------|--------------|
| USER_ID | Mailbox name (e.g., `alice`) |
| Common Name (CN) | Human-readable blurb (e.g., `Alice Smith`) |
| SAN DNS | Hostname (e.g., `example.com`) |

This layout embeds the full Misfin address (`alice@example.com`) and an optional display name directly in the certificate. The client extracts its own identity from the certificate and includes it in the gemmail sender metadata before sending.

## Trust-On-First-Use (TOFU)

TOFU works like SSH's `known_hosts`:

1. **First connection:** The server's certificate fingerprint is stored in the TOFU database
2. **Subsequent connections:** The fingerprint is compared against the stored value
3. **Mismatch:** A `CertificateChangedError` is raised, indicating a potential man-in-the-middle attack

The TOFU database is managed by tlacacoca's `TOFUDatabase`. Users can list and revoke stored fingerprints via the CLI (`titlani tofu list`, `titlani tofu revoke`).

### Limitations

TOFU is vulnerable to attacks on the first connection (before a fingerprint is stored). In practice, this is acceptable for a decentralized protocol where there is no CA to provide initial trust.

## Fingerprint Bridge

Tlacacoca returns fingerprints in `sha256:hexdigest` format (e.g., `sha256:A1B2C3...`), but Misfin(C) uses plain lowercase hex (e.g., `a1b2c3...`).

The `normalize_fingerprint()` function handles this conversion at every boundary:

- Strips the algorithm prefix (`sha256:`, `sha1:`, etc.)
- Removes non-hex characters
- Lowercases the result

This function is called whenever fingerprints cross between tlacacoca and Misfin code paths (client certificate verification, TOFU storage, response meta field).

## Sender Verification

Because the server cannot request TLS client certificates (see above), sender identity in the gemmail metadata is self-reported. Sender verification adds a probe-based check: before accepting a message, the receiving server sends a zero-length request to the claimed sender's address and checks whether the sender's server acknowledges the mailbox.

### What It Proves

| Property | Verified? |
|----------|-----------|
| Sender's hostname has a running Misfin server | Yes |
| Claimed mailbox exists on that server | Yes |
| The connecting client owns that mailbox | **No** |
| The message was not tampered with | **No** |

Probe-based verification is an anti-forgery measure: it prevents a client from claiming to be `alice@example.com` if `example.com`'s server does not recognize that mailbox. It does **not** authenticate the sender — a different person could still send messages with a valid sender address.

### Verification Modes

- **Off** (default) — No verification. Matches the behavior before this feature existed.
- **Optional** — Probes are sent, but unverified messages are still delivered. Useful for monitoring.
- **Required** — Unverified messages are rejected with status **61** (unauthorized sender).

### Verification Cache

Results are cached in a SQLite database keyed by sender address. Once a sender is verified, subsequent messages from the same address skip the probe. The cache does not currently expire entries — revocation must be done manually.

### Security Considerations

- **Amplification attacks** — A malicious client could forge sender addresses from victim servers, causing the receiving server to probe the victim. Rate limiting mitigates this.
- **Mailbox enumeration** — Verification probes reveal whether a mailbox exists on a server. This is inherent to the design.
- **No replay protection** — A cached verification result does not prevent replayed or spoofed messages from a valid sender address.

For stronger sender authentication, TLS client certificates would need to be re-enabled (pending a solution to the OpenSSL 3.x issue described above).

See [Sender Verification How-To](../how-to/sender-verification.md) for configuration details.

## At-Rest Encryption

Misfin's transport layer (mandatory TLS) protects messages in transit, but delivered messages are stored as plaintext `.gemmail` files by default. At-rest encryption protects stored messages so that only the mailbox owner's private key can decrypt them.

### Cryptographic Scheme

Titlani uses an ECIES-like construction:

| Component | Algorithm | Purpose |
|-----------|-----------|---------|
| Key agreement | X25519 ECDH | Derive a shared secret between ephemeral and recipient keys |
| Key derivation | HKDF-SHA256 | Derive a 256-bit symmetric key with domain separation |
| Authenticated encryption | AES-256-GCM | Encrypt and integrity-protect the message |

Each encryption generates a fresh ephemeral X25519 keypair. The shared secret is derived via ECDH between the ephemeral private key and the recipient's long-term public key, then fed through HKDF with the info string `titlani-mailbox-encryption` and no salt (the ephemeral key provides per-message uniqueness). The resulting 256-bit key encrypts the message via AES-256-GCM with a random 12-byte nonce.

The wire format is: `[32B ephemeral public key][12B nonce][ciphertext + 16B GCM tag]`.

### Key Separation Model

The security model enforces a strict separation between the server (encrypt-only) and users (decrypt):

- **Server process** loads only **public keys** (`.enc.pub`). It can encrypt incoming messages but cannot decrypt any stored mail.
- **Each user** holds their own **private key** (`.enc.key`) with `0600` permissions. Only they can decrypt their mail via the CLI.

This means a compromised server process cannot read previously stored encrypted messages. However, the server does see messages in plaintext briefly during receipt (before encrypting to disk) — at-rest encryption does not protect against a compromised server process reading messages as they arrive.

### What At-Rest Encryption Protects Against

| Threat | Protected? |
|--------|------------|
| Disk theft or unauthorized file access | Yes |
| Backup exposure (unencrypted backups of mailbox storage) | Yes |
| Compromised server reading stored mail | Yes |
| Compromised server reading messages during receipt | **No** |
| Tampered ciphertext (bit-flipping, truncation) | Yes (GCM tag verification fails) |
| Key compromise of one mailbox affecting others | **No** (each mailbox has its own keypair) |

### Why X25519 Instead of RSA or the Identity Certificate Key

Misfin identity certificates use RSA keys for TLS. At-rest encryption uses a separate X25519 keypair because:

1. **Key separation** — The identity key is used for TLS authentication; the encryption key is used for at-rest confidentiality. Compromising one does not compromise the other.
2. **ECDH suitability** — X25519 is purpose-built for Diffie-Hellman key agreement, enabling the ECIES construction where each message uses a fresh ephemeral key. RSA encryption (OAEP) would work but limits message size and doesn't provide forward secrecy per message.
3. **Performance** — X25519 operations are significantly faster than RSA operations, relevant when encrypting every incoming message.

See [At-Rest Encryption How-To](../how-to/at-rest-encryption.md) for setup instructions.

## GMAP Authentication

When GMAP is enabled, the server accepts Gemini protocol requests for remote mailbox access. GMAP authenticates clients using Misfin identity certificates:

1. **Certificate extraction** — After the TLS handshake, the server extracts the client certificate from the transport (via `getpeercert`)
2. **Identity extraction** — The server reads the USER_ID (mailbox) and SAN DNS (hostname) from the certificate
3. **Mailbox authorization** — The client can only access the mailbox matching their certificate's USER_ID

### Why Application-Layer Auth

GMAP uses the same TLS context as Misfin (`request_client_cert=False`), extracting client certificates at the application layer rather than requiring them at the TLS level. This avoids the OpenSSL 3.x `CERT_OPTIONAL` issue described above. If no client certificate is presented, the GMAP handler returns Gemini status 60 (Client Certificate Required).

### Path Traversal Protection

The mailbox name extracted from the client certificate is validated with the same protections used by the Misfin handler:

- Regex validation: `[a-zA-Z0-9._-]+` only
- Blocks null bytes, slashes, backslashes, and `..` sequences
- Symlink-safe path resolution to verify the resolved path is inside the mailbox directory

### What GMAP Auth Proves

| Property | Verified? |
|----------|-----------|
| Client holds a valid Misfin identity certificate | Yes |
| Client can only access their own mailbox | Yes |
| Certificate was issued by a trusted authority | **No** (self-signed certificates) |
| Client is who they claim to be | **No** (same TOFU limitation as Misfin) |

## DoS Protections

The protocol includes built-in limits to prevent denial-of-service attacks:

| Protection | Limit | Constant |
|------------|-------|----------|
| Maximum header size | 1024 bytes | `MAX_HEADER_SIZE` |
| Maximum message body | 16384 bytes | `MAX_CONTENT_LENGTH` |
| Maximum metadata line | 1024 bytes | `MAX_METADATA_LINE_SIZE` |
| Maximum response size | 2048 bytes | `MAX_RESPONSE_SIZE` |
| Maximum Gemini request | 1024 bytes | `MAX_GEMINI_REQUEST_SIZE` |
| Request timeout | 30 seconds | `REQUEST_TIMEOUT` |
| Maximum redirects | 5 hops | `MAX_REDIRECTS` |
| Protocol detection timeout | 30 seconds | `REQUEST_TIMEOUT` |

The server protocol enforces these limits during the two-phase buffering process, closing connections that exceed them.

## Middleware

The server supports pluggable middleware via tlacacoca's `MiddlewareChain`:

### Rate Limiting

Token bucket rate limiting per client IP. When the bucket is empty, the server responds with status **44** (slow down). Configurable via the `[rate_limit]` TOML section.

### Access Control

IP-based allow/deny lists. Denied clients receive status **53** (domain not serviced). Configurable via the `[access_control]` TOML section.

### Middleware-to-Status Mapping

When middleware denies a request, the server maps tlacacoca's `DenialReason` to Misfin status codes:

| Denial Reason | Misfin Status |
|---------------|---------------|
| `RATE_LIMIT` | 44 (SLOW_DOWN) |
| `ACCESS_DENIED` | 53 (DOMAIN_NOT_SERVICED) |
| `CERT_REQUIRED` | 60 (CERTIFICATE_REQUIRED) |
| `CERT_NOT_AUTHORIZED` | 61 (UNAUTHORIZED_SENDER) |
