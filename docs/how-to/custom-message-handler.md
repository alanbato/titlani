# Custom Message Handler

The default `FileMailboxHandler` stores messages as `.gemmail` files. You can implement custom delivery logic by subclassing `MessageHandler`.

## Define a Handler

```python
from titlani import MessageHandler, MisfinRequest, MisfinResponse, StatusCode


class DatabaseHandler(MessageHandler):
    """Store messages in a database instead of files."""

    def __init__(self, db_connection):
        self.db = db_connection

    async def handle_message(self, request: MisfinRequest) -> MisfinResponse:
        try:
            # Parse the gemmail message
            message = request.parse_message()
        except ValueError:
            return MisfinResponse(
                status=StatusCode.BAD_REQUEST,
                meta="Invalid message format",
            )

        # Store in database
        await self.db.insert_message(
            mailbox=request.mailbox,
            hostname=request.hostname,
            senders=message.senders,
            body=message.body,
            received_at=message.timestamps[0] if message.timestamps else None,
        )

        # Return success with recipient fingerprint
        return MisfinResponse(
            status=StatusCode.SUCCESS,
            meta="delivered",
        )
```

## Handler Contract

Your `handle_message` method receives a `MisfinRequest` with:

- `request.mailbox` — Target mailbox name
- `request.hostname` — Target hostname
- `request.raw_message` — Raw message bytes
- `request.content_length` — Message body length
- `request.client_cert` — Sender's TLS certificate (if provided)
- `request.client_cert_fingerprint` — Normalized fingerprint of sender's cert

Return a `MisfinResponse` with an appropriate [status code](../reference/status-codes.md):

| Status | When to use |
|--------|-------------|
| 20 (SUCCESS) | Message delivered successfully |
| 45 (MAILBOX_FULL) | Mailbox cannot accept more messages |
| 51 (MAILBOX_NOT_FOUND) | Mailbox doesn't exist |
| 53 (DOMAIN_NOT_SERVICED) | Hostname not handled by this server |
| 59 (BAD_REQUEST) | Message format is invalid |

## Wire to the Server

To use a custom handler, you currently need to build the server manually using the lower-level components:

```python
import asyncio
import ssl

from titlani.server.protocol import MisfinServerProtocol


async def run_custom_server(handler, ssl_context, host, port):
    loop = asyncio.get_event_loop()
    server = await loop.create_server(
        lambda: MisfinServerProtocol(handler.handle_message),
        host,
        port,
        ssl=ssl_context,
    )
    async with server:
        await server.serve_forever()
```

The `MisfinServerProtocol` handles the two-phase buffering (header + body), TLS, timeouts, and size limits. Your handler only needs to process the fully-parsed request.
