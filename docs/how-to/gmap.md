# GMAP (Remote Mailbox Access)

GMAP (Gemini Mailbox Access Protocol) lets clients retrieve and manage mailbox contents remotely over Gemini protocol. When enabled, the Titlani server serves mailbox messages alongside the normal Misfin mail transport — both on the same port.

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
```

That's it. The server now accepts both Misfin (`misfin://`) and Gemini (`gemini://`) requests on port 1958.

## How It Works

When a client connects, the server inspects the first bytes to detect the protocol:

- `misfin://` — handled as a normal Misfin mail delivery
- `gemini://` — routed to the GMAP handler

GMAP clients authenticate using the same Misfin identity certificate they use for sending mail. The server extracts the mailbox name from the client certificate's USER_ID field and grants access only to that mailbox.

## Client Certificate Setup

GMAP clients must present their Misfin identity certificate during the TLS handshake. The certificate must contain:

- **USER_ID** — the mailbox name (e.g., `alice`)
- **SAN DNS** — the server hostname (e.g., `mail.example.com`)

This is the same certificate format used for sending mail:

```bash
titlani identity generate alice mail.example.com --blurb "Alice"
```

## Available Routes

All routes use Gemini URLs on the Misfin port (default 1958).

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
    20260211T120000Z.gemmail
    20260211T130000Z.gemmail.enc
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

- New `.gemmail` or `.gemmail.enc` files are discovered and auto-tagged with `Inbox` and `Unread`
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

[encryption]
enable = true
key_dir = "/etc/titlani/keys"

[rate_limit]
enable = true
capacity = 20
refill_rate = 2.0
```

## Security Considerations

- **Authentication**: GMAP authenticates clients via their Misfin identity certificate. The mailbox name extracted from the certificate's USER_ID determines which mailbox the client can access. There is no cross-mailbox access.
- **Path traversal**: Mailbox names are validated with the same regex and symlink-safe path resolution used by the Misfin handler.
- **Rate limiting**: When enabled, the existing rate limiting middleware applies to both Misfin and GMAP requests.
- **TLS**: GMAP runs over the same TLS connection as Misfin. Client certificates are extracted at the application layer after the TLS handshake (the same approach used for Misfin sender identity).
