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

This is a protocol-level limitation shared by Misfin implementations on modern TLS stacks, not specific to Titlani. Messages are also not encrypted at rest — intermediaries with access to the server's storage can read delivered messages, even though the transport is encrypted.

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

## DoS Protections

The protocol includes built-in limits to prevent denial-of-service attacks:

| Protection | Limit | Constant |
|------------|-------|----------|
| Maximum header size | 1024 bytes | `MAX_HEADER_SIZE` |
| Maximum message body | 16384 bytes | `MAX_CONTENT_LENGTH` |
| Maximum metadata line | 1024 bytes | `MAX_METADATA_LINE_SIZE` |
| Maximum response size | 2048 bytes | `MAX_RESPONSE_SIZE` |
| Request timeout | 30 seconds | `REQUEST_TIMEOUT` |
| Maximum redirects | 5 hops | `MAX_REDIRECTS` |

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
