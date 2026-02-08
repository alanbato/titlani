# Running a Mail Server

In this tutorial you will set up a Misfin server, create mailbox directories, deliver a test message, and inspect the stored `.gemmail` file.

**Time:** ~15 minutes | **Difficulty:** Beginner

## Prerequisites

- Titlani installed (`titlani version` works)
- A sender identity certificate (see [Sending Your First Message](sending-your-first-message.md))

## Step 1: Create a Config File

Create `server.toml`:

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "example.com"
mailbox_dir = "mailboxes"
```

!!! note
    If you omit `certfile` and `keyfile`, the server auto-generates temporary TLS certificates on startup. For production, provide your own.

## Step 2: Create Mailbox Directories

Each mailbox is a directory under `mailbox_dir`:

```bash
mkdir -p mailboxes/bob
mkdir -p mailboxes/carol
```

Messages sent to `bob@example.com` will be stored in `mailboxes/bob/`.

## Step 3: Start the Server

```bash
titlani serve --config server.toml
```

You should see:

```
Starting Misfin server on 0.0.0.0:1958 for example.com
```

The server is now listening for incoming Misfin messages. Leave it running.

## Step 4: Send a Test Message

Open another terminal and send a message:

```bash
titlani send bob@localhost "Hello, Bob! This is a test." \
    --cert alice.pem --key alice.key \
    --subject "Test message"
```

!!! tip
    Use `bob@localhost` since the server is running locally. In production, use the actual hostname.

If the server hostname doesn't match, you'll get status **53** (domain not serviced). Make sure the address hostname matches the server's configured `hostname`, or use `localhost` for testing.

## Step 5: Check the Delivered Message

Look in the mailbox directory:

```bash
ls mailboxes/bob/
```

You should see a file like `2025-01-15T10_30_45.gemmail`. Read it:

```bash
cat mailboxes/bob/*.gemmail
```

The gemmail format has three metadata lines followed by the message body:

```
alice@example.com Alice Smith
bob@example.com
2025-01-15T10:30:45+00:00
# Test message
Hello, Bob! This is a test.
```

The lines are:

1. **Senders** — Comma-separated addresses with optional blurbs
2. **Recipients** — Comma-separated addresses
3. **Timestamps** — Comma-separated ISO 8601 timestamps in UTC
4. **Body** — Gemtext content (subject appears as a `#` heading)

## Step 6: Enable Rate Limiting (Optional)

Add rate limiting to your config:

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "example.com"
mailbox_dir = "mailboxes"

[rate_limit]
enable = true
capacity = 10
refill_rate = 1.0
retry_after = 30
```

Restart the server. Clients that send too many messages will receive status **44** (slow down).

## What You Learned

- How to create a server configuration file
- How to set up mailbox directories
- How to start the Misfin server
- The structure of stored `.gemmail` files
- How to enable rate limiting

## Next Steps

- [Configure Server](../how-to/configure-server.md) — Full TOML config reference
- [Rate Limiting](../how-to/rate-limiting.md) — Tune the token bucket
- [Access Control](../how-to/access-control.md) — Allow/deny lists
- [Building a Mail Client](building-a-mail-client.md) — Use the Python API
