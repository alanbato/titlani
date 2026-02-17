# Titlani

**Misfin(C) mail protocol client and server library for Python.**

Titlani is a complete implementation of the [Misfin(C)](https://misfin.org/) mail transport protocol -- a lightweight, privacy-focused mail protocol influenced by Gemini that uses mandatory TLS with self-signed identity certificates and Trust-On-First-Use (TOFU) validation.

## Features

- **Full Misfin(C) protocol** -- Wire format parsing, status codes, gemmail message format
- **Async client and server** -- Built on `asyncio.Protocol` with TLS, TOFU, redirect handling, and middleware
- **Identity certificates** -- Generate and manage Misfin identity certs with custom layout (USER_ID, CN, SAN DNS)
- **At-rest encryption** -- Per-mailbox X25519 ECDH + AES-256-GCM encryption for stored messages
- **Sender verification** -- Probe-based and SPKI-based verification with SQLite caching
- **GMAP** -- Gemini Mailbox Access Protocol for remote mailbox access with tag management
- **Mailing lists** -- Server-side mailing list support with subscriber management and message forwarding
- **Rate limiting and access control** -- Token bucket rate limiting and IP allow/deny lists via tlacacoca
- **Contact blocking** -- Per-mailbox sender block lists
- **Auto-reply** -- Server-side out-of-office automatic replies with loop prevention
- **CLI tool** -- Full-featured `titlani` command for sending, serving, reading mail, and administration

## Installation

```bash
uv add titlani
```

Or with pip:

```bash
pip install titlani
```

Requires **Python 3.13+**.

## Quick Start

Generate an identity, send a message, and start a server:

```bash
# Generate an identity certificate
titlani identity generate alice example.com --blurb "Alice Smith"

# Send a message
titlani send bob@remote.host "Hello from Misfin!" \
    --cert alice.pem --key alice.key --subject "Greetings"

# Generate server and client config interactively
titlani init

# Start a server (auto-discovers config from ~/.config/titlani/)
titlani serve

# List and read your mail
titlani mail list
titlani mail read 1
```

Or use the Python API:

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
            body="Hello from Misfin!",
            subject="Greetings",
        )
        print(f"{response.status} {response.meta}")

asyncio.run(main())
```

## Documentation

Full documentation is available at [titlani.readthedocs.io](https://titlani.readthedocs.io):

- [**Quick Start**](https://titlani.readthedocs.io/quickstart/) -- Core workflow in 6 steps
- [**Tutorials**](https://titlani.readthedocs.io/tutorials/) -- Step-by-step guides for sending messages, running servers, and building clients
- [**How-To Guides**](https://titlani.readthedocs.io/how-to/) -- Recipes for encryption, verification, GMAP, mailing lists, and more
- [**CLI Reference**](https://titlani.readthedocs.io/reference/cli/) -- All `titlani` commands and options
- [**Configuration Reference**](https://titlani.readthedocs.io/reference/configuration/) -- Server and client TOML config
- [**API Reference**](https://titlani.readthedocs.io/reference/api/) -- Python API documentation

## License

See [LICENSE](LICENSE) for details.
