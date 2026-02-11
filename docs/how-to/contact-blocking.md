# Contact Blocking

Block specific sender addresses from delivering messages to a mailbox. Blocked senders receive status **61** (Unauthorized Sender) and their messages are not stored.

## How It Works

Each mailbox can have a `.blocked` file containing one sender address per line. When a message arrives, the server checks both the client certificate identity and the gemmail metadata senders against the block list. If any sender address matches, the message is rejected before storage.

```
mailboxes/
  alice/
    .blocked                          ← one address per line
    20260211T120000Z.gemmail.new
```

## Block a Sender via CLI

```bash
titlani mail block spam@evil.com --mailbox alice
```

This creates or appends to the `.blocked` file in Alice's mailbox directory.

To specify a non-default mailbox directory:

```bash
titlani mail block spam@evil.com -d /var/mail/misfin -m alice
```

## Unblock a Sender

```bash
titlani mail unblock spam@evil.com --mailbox alice
```

If the address was the only entry, the `.blocked` file is removed entirely.

## View Blocked Addresses

The `.blocked` file is a plain text file you can inspect directly:

```bash
cat mailboxes/alice/.blocked
```

## Matching Rules

- Addresses are compared **case-insensitively** — blocking `Spam@Evil.com` also blocks `spam@evil.com`
- Both the TLS client certificate identity and all senders listed in the gemmail metadata are checked
- Empty lines and whitespace are ignored
- If the `.blocked` file is missing or empty, all senders are allowed

## Manual Editing

You can edit the `.blocked` file directly. One address per line, `mailbox@hostname` format:

```
spam@evil.com
bulk@newsletters.example
```

Changes take effect on the next incoming message — no server restart needed.

## Server Behavior

When a blocked sender attempts delivery:

1. The server parses the sender identity from the client certificate and gemmail metadata
2. Each sender address is checked against the recipient's `.blocked` file
3. On match, the server returns status **61** with meta `"Sender blocked"` and logs a `sender_blocked` event
4. The message is never stored

!!! note
    Blocking happens before message storage and encryption. Blocked messages consume no disk space.
