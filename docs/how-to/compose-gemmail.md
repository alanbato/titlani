# Compose Gemmail

Gemmail is the message format used by Misfin. It consists of three metadata lines followed by a gemtext body.

## Message Structure

```
sender1@host1 Blurb One, sender2@host2
recipient1@host1, recipient2@host2
2025-01-15T10:30:45+00:00
# Subject Line
Message body in gemtext format.
```

1. **Senders** — Comma-separated `mailbox@hostname [blurb]` addresses
2. **Recipients** — Comma-separated `mailbox@hostname [blurb]` addresses
3. **Timestamps** — Comma-separated ISO 8601 timestamps in UTC
4. **Body** — Gemtext content

## Build a Message

```python
from datetime import datetime, timezone
from titlani import GemmailMessage, MisfinAddress

message = GemmailMessage(
    senders=[MisfinAddress(mailbox="alice", hostname="example.com", blurb="Alice Smith")],
    recipients=[MisfinAddress(mailbox="bob", hostname="remote.host")],
    timestamps=[datetime.now(timezone.utc)],
    body="# Meeting Notes\n\nDiscussed the roadmap.\n",
)
```

## Parse Addresses

`MisfinAddress.parse()` accepts the string format `mailbox@hostname [blurb]`:

```python
addr = MisfinAddress.parse("alice@example.com Alice Smith")
print(addr.mailbox)    # "alice"
print(addr.hostname)   # "example.com"
print(addr.blurb)      # "Alice Smith"
print(addr.address)    # "alice@example.com"
print(addr.long_form)  # "Alice Smith (alice@example.com)"
```

Addresses without a blurb:

```python
addr = MisfinAddress.parse("bob@remote.host")
print(addr.blurb)      # ""
print(str(addr))        # "bob@remote.host"
```

## Serialize and Deserialize

Convert to bytes for sending:

```python
raw = message.to_bytes()
```

Parse from received bytes:

```python
parsed = GemmailMessage.from_bytes(raw)
```

`from_bytes()` validates:

- UTF-8 encoding
- CR only appears before LF (no bare CRs)
- At least 3 metadata lines present
- Metadata line size limits (1024 bytes each)

## Extract Subject

The `subject` property extracts the first `#` or `##` heading from the body:

```python
message = GemmailMessage(
    senders=[],
    recipients=[],
    timestamps=[],
    body="# Important Update\n\nDetails here.\n",
)
print(message.subject)  # "Important Update"
```

Returns `None` if no heading is found.

## Send with MisfinClient

Use `send_raw()` for pre-built messages:

```python
async with MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
) as client:
    response = await client.send_raw(
        to="bob@remote.host",
        message_bytes=message.to_bytes(),
    )
```

Or let `send()` build the message for you:

```python
response = await client.send(
    to="bob@remote.host",
    body="Hello!",
    subject="Greetings",
)
```
