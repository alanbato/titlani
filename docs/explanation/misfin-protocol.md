# Misfin Protocol

Misfin is a lightweight mail transport protocol influenced by [Gemini](https://geminiprotocol.net/). It uses mandatory TLS with self-signed identity certificates and Trust-On-First-Use (TOFU) validation.

## History

Misfin was designed as a companion to Gemini — a minimalist, privacy-focused alternative to email. While Gemini provides a simple request-response protocol for document retrieval, Misfin adds asynchronous message delivery.

### Misfin(B)

The earlier Misfin(B) variant established the core concepts:

- TLS-only connections with self-signed certificates
- Identity through certificates rather than passwords
- Simple status code system borrowed from Gemini
- Gemtext as the message body format

### Misfin(C)

Misfin(C) refines the protocol with:

- **Explicit content length** in the request header, enabling the two-phase parsing model
- **Gemmail message format** with structured metadata (senders, recipients, timestamps)
- **Certificate-based identity** with a specific certificate layout (USER_ID for mailbox, CN for blurb, SAN DNS for hostname)

Titlani implements Misfin(C).

## Wire Format

### Request

```
misfin://<mailbox>@<hostname>\t<content-length>\r\n<message-body>
```

- **Scheme:** Always `misfin://`
- **Address:** `mailbox@hostname` — the recipient
- **Tab separator** between the URL and content length
- **Content length:** Decimal byte count of the message body
- **CRLF** terminates the header line
- **Message body:** Exactly `content-length` bytes of gemmail content

The maximum header size is 1024 bytes. The maximum content length is 16384 bytes.

### Response

```
<status> <meta>\r\n
```

- **Status:** Two-digit integer (see [Status Codes](../reference/status-codes.md))
- **Space separator**
- **Meta:** Context-dependent string (fingerprint on success, redirect address, or error message)
- **CRLF** terminates the response

The maximum response size is 2048 bytes.

### Gemmail Message Format

The message body uses the gemmail format — three metadata lines followed by gemtext:

```
sender1@host1 Blurb, sender2@host2
recipient1@host1, recipient2@host2
2025-01-15T10:30:45+00:00
# Subject
Body text in gemtext format.
```

1. **Senders** — Comma-separated `mailbox@hostname [blurb]`
2. **Recipients** — Comma-separated `mailbox@hostname [blurb]`
3. **Timestamps** — Comma-separated ISO 8601 timestamps in UTC
4. **Body** — Gemtext content (subject extracted from first heading)

## Comparison with SMTP

| Aspect | Misfin(C) | SMTP |
|--------|-----------|------|
| **Transport** | TLS-only, port 1958 | Plaintext or STARTTLS, port 25/587 |
| **Authentication** | Self-signed client certificates | Username/password, SPF, DKIM, DMARC |
| **Trust model** | TOFU (like SSH) | CA-based PKI |
| **Message format** | Gemmail (gemtext body) | MIME (HTML, attachments, etc.) |
| **Max message size** | 16 KB | Typically 10-25 MB |
| **Header complexity** | 1 line (URL + content length) | Many headers (From, To, Subject, etc.) |
| **Spam prevention** | Certificate identity + middleware | Complex ecosystem (SPF, DKIM, DMARC, bayesian filters) |

Misfin deliberately trades features for simplicity. There are no attachments, no HTML, no threading, and no delivery receipts. The protocol trusts that simplicity and mandatory identity certificates naturally reduce abuse.

## Default Port

Misfin uses port **1958** by default, defined as `DEFAULT_PORT` in the protocol constants.
