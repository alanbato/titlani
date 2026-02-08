# Building a Mail Client

In this tutorial you will use Titlani's async Python API to send messages, handle responses, work with TOFU, and build custom gemmail messages.

**Time:** ~20 minutes | **Difficulty:** Intermediate

## Prerequisites

- Titlani installed
- A sender identity certificate (`alice.pem` and `alice.key`)
- A running Misfin server to test against
- Basic familiarity with Python's `asyncio`

## Step 1: Create a Simple Client

The `MisfinClient` is an async context manager that handles TLS connections and TOFU:

```python
import asyncio
from titlani import MisfinClient

async def main():
    async with MisfinClient(
        client_cert="alice.pem",
        client_key="alice.key",
    ) as client:
        response = await client.send(
            to="bob@example.com",
            body="Hello from Python!",
            subject="First programmatic message",
        )
        print(f"Status: {response.status}")
        print(f"Meta: {response.meta}")

asyncio.run(main())
```

The `send()` method:

1. Builds a `GemmailMessage` with sender info extracted from your certificate
2. Serializes it to the Misfin wire format
3. Opens a TLS connection to the recipient's host
4. Sends the request and reads the response
5. Follows redirects automatically (up to 5 hops)

## Step 2: Handle Response Status

Check the response status to determine what happened:

```python
from titlani import StatusCode
from titlani.protocol.status import is_success, is_redirect, is_error

async def send_with_handling(client, to, body):
    response = await client.send(to=to, body=body)

    if is_success(response.status):
        print(f"Delivered! Recipient fingerprint: {response.fingerprint}")
    elif is_error(response.status):
        print(f"Error {response.status}: {response.meta}")
    else:
        print(f"Unexpected status: {response.status} {response.meta}")

    return response
```

## Step 3: TOFU (Trust-On-First-Use)

By default, `MisfinClient` enables TOFU. The first time you connect to a server, its certificate fingerprint is stored. On subsequent connections, the fingerprint is verified.

```python
from tlacacoca import CertificateChangedError

async def send_with_tofu(client, to, body):
    try:
        response = await client.send(to=to, body=body)
        return response
    except CertificateChangedError as e:
        print(f"Certificate changed for {e.hostname}!")
        print(f"Expected: {e.expected_fingerprint}")
        print(f"Got:      {e.actual_fingerprint}")
        print("This could indicate a man-in-the-middle attack.")
        raise
```

You can customize TOFU behavior:

```python
from pathlib import Path

# Custom TOFU database location
client = MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
    tofu_db_path=Path("~/.titlani/known_hosts.db"),
)

# Disable TOFU entirely
client = MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
    trust_on_first_use=False,
)
```

## Step 4: Build Custom Messages

For more control over the message format, build a `GemmailMessage` directly:

```python
from datetime import datetime, timezone
from titlani import GemmailMessage, MisfinAddress, MisfinClient

async def send_custom_message():
    # Create addresses
    sender = MisfinAddress.parse("alice@example.com Alice Smith")
    recipient = MisfinAddress.parse("bob@remote.host Bob Jones")

    # Build the message
    message = GemmailMessage(
        senders=[sender],
        recipients=[recipient],
        timestamps=[datetime.now(timezone.utc)],
        body="# Meeting Notes\n\nHere are the notes from today's meeting.\n\n## Action Items\n\n* Review the proposal\n* Send feedback by Friday\n",
    )

    # Serialize and send
    async with MisfinClient(
        client_cert="alice.pem",
        client_key="alice.key",
    ) as client:
        response = await client.send_raw(
            to="bob@remote.host",
            message_bytes=message.to_bytes(),
        )
        print(f"Status: {response.status}")

asyncio.run(send_custom_message())
```

The `send_raw()` method sends pre-formatted message bytes, giving you full control over the gemmail content.

## Step 5: Configure Timeouts and Ports

Customize connection parameters:

```python
client = MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
    timeout=10.0,   # 10-second timeout (default: 30)
    port=1959,       # Non-standard port (default: 1958)
)
```

## What You Learned

- How to use `MisfinClient` as an async context manager
- How to send messages with `send()` and `send_raw()`
- How to handle response status codes
- How to work with TOFU and handle `CertificateChangedError`
- How to build custom `GemmailMessage` objects
- How to configure timeouts and ports

## Next Steps

- [Compose Gemmail](../how-to/compose-gemmail.md) — Detailed gemmail format guide
- [Manage TOFU](../how-to/manage-tofu.md) — TOFU database operations
- [API Reference: Client](../reference/api/client.md) — Full `MisfinClient` API
