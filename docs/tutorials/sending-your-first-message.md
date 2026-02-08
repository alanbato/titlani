# Sending Your First Message

In this tutorial you will install Titlani, generate a Misfin identity certificate, and send your first message using the CLI.

**Time:** ~10 minutes | **Difficulty:** Beginner

## Prerequisites

- Python 3.13+
- A Misfin server to send to (or use a test server)

## Step 1: Install Titlani

```bash
uv add titlani
```

Or with pip:

```bash
pip install titlani
```

Verify the installation:

```bash
titlani version
```

## Step 2: Generate Your Identity

Every Misfin participant is identified by a self-signed certificate. Generate yours:

```bash
titlani identity generate alice example.com --blurb "Alice Smith"
```

This creates:

| File | Description |
|------|-------------|
| `alice.pem` | Your identity certificate |
| `alice.key` | Your private key |

!!! warning
    Keep `alice.key` secret. Anyone with your private key can impersonate you.

Inspect your new identity:

```bash
titlani identity info alice.pem
```

```
Address:     alice@example.com
Blurb:       Alice Smith
Hostname:    example.com
Fingerprint: a1b2c3d4e5f6...
Not Before:  2025-01-01 00:00:00
Not After:   2026-01-01 00:00:00
```

The identity embeds your mailbox name, hostname, and blurb directly in the certificate using Misfin-specific fields.

## Step 3: Send a Message

Now send a message to another Misfin address:

```bash
titlani send bob@remote.host "Hello from Misfin!" \
    --cert alice.pem --key alice.key \
    --subject "Greetings"
```

The `--subject` flag prepends a `# Greetings` heading to the message body.

## Step 4: Read the Response

The server responds with a status code and metadata:

```
20 a1b2c3d4e5f6...
```

This means:

- **20** — Success! The message was delivered.
- **a1b2c3d4...** — The recipient's certificate fingerprint.

If something went wrong, you might see:

| Status | Meaning |
|--------|---------|
| 51 | Mailbox not found |
| 53 | Domain not serviced by this server |
| 59 | Bad request (malformed message) |
| 60 | Certificate required |

See the full [Status Codes reference](../reference/status-codes.md) for details.

## What You Learned

- How to generate a Misfin identity certificate
- How to send a message with the `titlani send` command
- How to interpret the server's response

## Next Steps

- [Running a Mail Server](running-a-mail-server.md) — Set up your own server to receive messages
- [Building a Mail Client](building-a-mail-client.md) — Use the Python API programmatically
