# Quick Start

This page walks you through the core Titlani workflow: generating an identity, sending a message, and running a server.

## 1. Generate an Identity

Every Misfin participant needs an identity certificate. Generate one with the CLI:

```bash
titlani identity generate alice example.com --blurb "Alice Smith"
```

This creates two files:

- `alice.pem` — Your identity certificate
- `alice.key` — Your private key (keep this secret!)

Inspect your identity:

```bash
titlani identity info alice.pem
```

## 2. Send a Message

Send a message to another Misfin address:

```bash
titlani send bob@remote.host "Hello, Bob!" \
    --cert alice.pem --key alice.key \
    --subject "First contact"
```

The response shows the delivery status:

```
20 <fingerprint>     # Success — message delivered
51 Mailbox not found  # The recipient doesn't exist
```

See [Status Codes](reference/status-codes.md) for all possible responses.

## 3. Start a Server

Run a Misfin server to receive messages:

```bash
mkdir -p mailboxes/bob
titlani serve --hostname example.com --mailbox-dir ./mailboxes
```

The server auto-generates TLS and identity certificates if not provided. Messages sent to `bob@example.com` are stored as `.gemmail` files in `mailboxes/bob/`.

For production use, create a [TOML config file](how-to/configure-server.md):

```toml
[server]
hostname = "example.com"
certfile = "server.pem"
keyfile = "server.key"
mailbox_dir = "mailboxes"
```

```bash
titlani serve --config server.toml
```

## 4. Programmatic Usage

Use the Python API for more control:

```python
import asyncio
from titlani import MisfinClient

async def main():
    async with MisfinClient(
        client_cert="alice.pem",
        client_key="alice.key",
    ) as client:
        response = await client.send(
            to="bob@remote.host",
            body="Hello from Python!",
            subject="Programmatic message",
        )
        print(f"Status: {response.status}")
        print(f"Meta: {response.meta}")

asyncio.run(main())
```

## Next Steps

- [Tutorials](tutorials/index.md) — Detailed walkthroughs
- [How-To Guides](how-to/index.md) — Recipes for specific tasks
- [API Reference](reference/api/index.md) — Full API documentation
