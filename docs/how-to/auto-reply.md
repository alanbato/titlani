# Auto-Reply

Set up automatic out-of-office replies for a mailbox. When enabled, the server sends a reply to the first sender of each incoming message using the contents of a `.auto-reply` file.

## Enable in Config

Add an `[auto_reply]` section to your server TOML config:

```toml
[auto_reply]
enable = true
interval = 86400
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable` | bool | `false` | Enable server-side auto-reply |
| `interval` | int | `86400` | Minimum seconds between auto-replies to the same sender |

## Set Up a Mailbox Auto-Reply

Create a `.auto-reply` file in the mailbox directory with the reply body:

```bash
echo "I'm currently away and will reply when I return." > mailboxes/alice/.auto-reply
```

The file contents become the full reply body. To disable auto-reply for a mailbox, delete the file:

```bash
rm mailboxes/alice/.auto-reply
```

No server restart is needed — the server checks for the file on each incoming message.

## How It Works

When a message is successfully delivered to a mailbox:

1. The server checks if `[auto_reply]` is enabled in the config
2. It looks for a `.auto-reply` file in the recipient's mailbox directory
3. If the file exists and the message passes safety checks, a reply is sent to the first sender
4. The reply uses the server's identity certificate and private key (`identity_certfile`/`identity_keyfile`)
5. The reply subject is set to `[Auto-Reply]`

Auto-replies are fire-and-forget — they never affect message delivery. If the reply fails (network error, timeout, rejected), the original message is still stored normally.

## Loop Prevention

The server prevents auto-reply loops:

- Messages with `[Auto-Reply]` in the subject are never auto-replied to
- This means two servers with auto-reply enabled will not create an infinite reply loop

## Rate Limiting

To avoid flooding a sender who sends multiple messages, the server rate-limits auto-replies per sender address:

- The `interval` setting controls the minimum time between replies to the same sender (default: 86400 seconds = 24 hours)
- The timestamp is recorded eagerly before sending, so concurrent messages from the same sender won't trigger duplicate replies

```toml
[auto_reply]
enable = true
interval = 3600   # reply at most once per hour per sender
```

!!! tip
    Set a shorter interval (e.g., `3600`) during active away periods when senders may write multiple times. Use the default `86400` for standard out-of-office notices.

## Requirements

Auto-reply requires the server to have identity credentials configured, since it sends messages as the server identity:

```toml
[server]
hostname = "mail.example.com"
identity_certfile = "identity.pem"
identity_keyfile = "identity.key"

[auto_reply]
enable = true
```

!!! warning
    If `identity_certfile` or `identity_keyfile` are not configured, auto-reply is silently skipped and an `auto_reply_no_identity_cert` warning is logged.

## Full Example

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
mailbox_dir = "/var/mail/misfin"
identity_certfile = "identity.pem"
identity_keyfile = "identity.key"

[auto_reply]
enable = true
interval = 86400
```

Then for each mailbox that should auto-reply:

```bash
echo "Thanks for your message! I'm away until March 1st." \
    > /var/mail/misfin/alice/.auto-reply
```
