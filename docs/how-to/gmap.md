# GMAP (Remote Mailbox Access)

GMAP (Gemini Mailbox Access Protocol) lets clients retrieve and manage mailbox contents remotely over Gemini protocol. When enabled, the Titlani server runs GMAP on a separate port (default 1960) alongside the normal Misfin mail transport (port 1958).

## Enable GMAP

Add a `[gmap]` section to your server TOML config:

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
mailbox_dir = "/var/lib/titlani/mailboxes"

[gmap]
enable = true
port = 1960
```

The server now listens on two ports: Misfin on 1958 and GMAP on 1960.

## Why a Separate Port?

Misfin and GMAP have conflicting TLS requirements:

- **Misfin** must NOT request client certificates — random senders present self-signed certs that would fail OpenSSL 3.x verification during the TLS handshake.
- **GMAP** must request client certificates — this is how mailbox owners authenticate.

These conflicting requirements mean they cannot share a TLS context, so GMAP runs on its own port. The GMAP specification explicitly allows any port.

## How It Works

The server creates two TLS contexts:

- **Misfin port (1958)**: `request_client_cert=False` — accepts mail from anyone
- **GMAP port (1960)**: `request_client_cert=True` — requires client certificate for authentication

GMAP clients authenticate using their Misfin identity certificate. The server verifies the certificate fingerprint against registered per-mailbox identity certificates and grants access only to the matching mailbox.

## Setting Up Users for GMAP

Use `--install` when generating identity certificates to register them for GMAP authentication:

```bash
# Generate cert and install it on the server
titlani identity generate alice mail.example.com \
    --blurb "Alice" \
    --install

# Or specify a custom server config
titlani identity generate alice mail.example.com \
    --install --config /etc/titlani/server.toml
```

The `--install` flag:

1. Copies `alice.pem` to the server's identity cert directory (used as a trusted CA cert for TLS and for fingerprint verification)
2. Creates the mailbox subdirectory if it doesn't exist
3. Prints the cert and key paths to share with the user

## Client Certificate Setup

GMAP clients must present their Misfin identity certificate during the TLS handshake. The certificate must contain:

- **USER_ID** — the mailbox name (e.g., `alice`)
- **SAN DNS** — the server hostname (e.g., `mail.example.com`)

The certificate fingerprint must match the one registered on the server (installed via `--install`).

## Available Routes

All routes use Gemini URLs on the GMAP port (default 1960).

### Retrieve a Message

```
gemini://mail.example.com/msgid/20260211T120000Z
```

Returns the message as `text/plain` in gemmail wire format (sender, recipient, timestamp metadata lines followed by the body).

### List Message IDs

```
gemini://mail.example.com/tag/
```

Returns a comma-separated list of all message IDs, excluding messages tagged Trash.

### List by Tag

```
gemini://mail.example.com/tag/Inbox
gemini://mail.example.com/tag/Unread
```

Returns comma-separated message IDs that have the specified tag. Messages tagged Trash are excluded (unless you query the Trash tag itself).

### Filter by Time

```
gemini://mail.example.com/tag/Inbox/2026-02-10T00:00:00Z
```

Returns only messages received since the given timestamp (ISO 8601 UTC).

### Add a Tag

```
gemini://mail.example.com/tag/Archive?20260211T120000Z
```

Adds the `Archive` tag to the specified message.

### Remove a Tag

```
gemini://mail.example.com/untag/Unread?20260211T120000Z
```

Removes the `Unread` tag from the specified message.

### Delete a Message

```
gemini://mail.example.com/delete?20260211T120000Z
```

Permanently deletes the message. The message **must** already be tagged `Trash` — the server returns an error otherwise. To delete a message:

1. Tag it as Trash: `gemini://host/tag/Trash?<msgid>`
2. Delete it: `gemini://host/delete?<msgid>`

## Tags

### Required Tags

GMAP defines six standard tags:

| Tag | Type | Description |
|-----|------|-------------|
| `Inbox` | Folder | New messages appear here |
| `Archive` | Folder | Kept mail not in Inbox or Trash |
| `Sent` | Folder | Messages sent by the user |
| `Drafts` | Folder | Composed but unsent messages |
| `Trash` | Status | Marked for deletion |
| `Unread` | Status | Not yet read |

### Auto-Tagging

When the Misfin server delivers a new message, the GMAP index automatically tags it with `Inbox` and `Unread`. This happens lazily — the index syncs with the filesystem on each GMAP request.

### Custom Tags

Users can create custom tags. Tag names must contain only letters, digits, underscores, and hyphens (regex: `[a-zA-Z0-9_-]+`).

### Trash Behavior

Messages tagged `Trash` are **hidden** from all other tag lists. For example, if a message has both `Inbox` and `Trash` tags, it will not appear in the Inbox listing — only in the Trash listing. When a message is removed from Trash (untagged), its other tags are restored.

## The Tag Index

GMAP maintains a `.gmap.json` file in each mailbox directory:

```
mailboxes/
  alice/
    .gmap.json                    ← tag index
    20260211T120000Z.gemmail.new  ← unread message
    20260211T130000Z.gemmail      ← read message
    20260211T140000Z.gemmail.enc  ← encrypted message
```

The index maps message IDs to their tags and timestamps:

```json
{
  "version": 1,
  "messages": {
    "20260211T120000Z": {
      "tags": ["Inbox", "Unread"],
      "timestamp": "2026-02-11T12:00:00Z",
      "filename": "20260211T120000Z.gemmail"
    }
  }
}
```

### Filesystem Sync

The index syncs with the filesystem on each GMAP request:

- New `.gemmail`, `.gemmail.new`, `.gemmail.enc`, and `.gemmail.enc.new` files are discovered and auto-tagged with `Inbox` and `Unread`
- When a `.new` file is renamed (e.g., the CLI marks it as read), the index updates the filename but preserves existing tags
- Files that have been deleted outside GMAP are removed from the index
- The index is written atomically (temp file + rename) to prevent corruption

### Message IDs

Message IDs are derived from the filename — the timestamp stem (e.g., `20260211T120000Z` from `20260211T120000Z.gemmail`). This is the ID used in all GMAP routes.

## Encrypted Messages

Messages stored with at-rest encryption (`.gemmail.enc` files) are tracked in the GMAP index like any other message — they can be tagged, listed, and deleted. However, retrieving them via `/msgid/<id>` returns a temporary failure (status 40) because the server does not have access to decryption keys.

## Gemini Status Codes

GMAP uses standard Gemini status codes:

| Status | Meaning |
|--------|---------|
| 20 | Success |
| 30 | Redirect (different host/port only) |
| 40 | Temporary failure (e.g., encrypted message) |
| 51 | Not found (message, mailbox, or route) |
| 59 | Bad request (invalid tag name, missing query) |
| 60 | Client certificate required |
| 61 | Certificate not authorized |

!!! note
    GMAP servers must not respond with 1x (input) status codes, per the specification.

## Full Server Config Example

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
mailbox_dir = "/var/lib/titlani/mailboxes"
certfile = "server.pem"
keyfile = "server.key"
identity_certfile = "identity.pem"
identity_keyfile = "identity.key"

[gmap]
enable = true
port = 1960

[encryption]
enable = true
key_dir = "/etc/titlani/keys"

[rate_limit]
enable = true
capacity = 20
refill_rate = 2.0
```

## Security Considerations

- **Fingerprint verification**: GMAP verifies that the client certificate fingerprint matches the registered identity for the mailbox. Simply creating a cert with the same `USER_ID` is not sufficient — the cert must be the exact one installed on the server.
- **Separate TLS contexts**: The GMAP port uses `request_client_cert=True` with per-mailbox `.pem` files as trusted CAs, while the Misfin port uses `request_client_cert=False` for untrusted senders.
- **Path traversal**: Mailbox names are validated with the same regex and symlink-safe path resolution used by the Misfin handler.
- **Graceful degradation**: If no per-mailbox certs are installed, GMAP still works but fingerprint verification is skipped (with a warning at server startup).
