# Mailing Lists

Titlani supports server-side mailing lists. When a message is sent to a list address, the server forwards it to all subscribers. Lists are managed via the CLI and configured in the server TOML config.

## Enable in Config

Add a `[lists]` section to your server TOML config:

```toml
[lists]
enable = true
archive = true
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable` | bool | `false` | Enable mailing list forwarding |
| `archive` | bool | `true` | Store a copy of forwarded messages in the list mailbox |

## Create a Mailing List

Use the CLI to create a new list:

```bash
titlani list create dev-announce
```

This creates a mailbox directory with a `subscribers.txt` file that marks it as a mailing list. The list name must contain only letters, digits, dots, dashes, and underscores.

To use a non-default mailbox directory:

```bash
titlani list create dev-announce -d /var/mail/misfin
```

## Manage Subscribers

### Admin-managed (CLI)

Add a subscriber with address verification (default):

```bash
titlani list add dev-announce alice@example.com -H mail.example.com
```

This sends a confirmation token to the address. The subscriber must reply with `confirm <TOKEN>` to complete the subscription. Use `--hostname` (or `-H`) to specify the server hostname for sending the confirmation message.

To skip verification and add directly (for migration or testing):

```bash
titlani list add dev-announce alice@example.com --no-verify
```

View subscribers (shows confirmed and pending status):

```bash
titlani list subscribers dev-announce
```

Output:

```
dev-announce subscribers (3):
  alice@example.com [confirmed]
  bob@remote.host [confirmed]
  carol@another.host [pending]
```

Remove a subscriber (also cleans up any pending verification):

```bash
titlani list remove dev-announce alice@example.com
```

### Self-service (via Misfin messages)

Users can manage their own subscriptions by sending messages to the list address with one of these commands as the message body:

| Command | Description |
|---------|-------------|
| `subscribe` | Request a subscription. The server sends a confirmation token back |
| `confirm <TOKEN>` | Confirm subscription with the 6-character hex token |
| `unsubscribe` | Remove yourself from the list |

Commands are case-insensitive and can optionally use a gemtext heading prefix (`# subscribe`). Command messages are never stored in the list archive or forwarded to subscribers.

**Example flow:**

1. Alice sends a message with body `subscribe` to `dev-announce@mail.example.com`
2. The server replies with a confirmation message containing a token (e.g., `A3F8B2`)
3. Alice sends a message with body `confirm A3F8B2` to `dev-announce@mail.example.com`
4. Alice is now subscribed and can post to the list

Self-service subscription requires the server to have mailing lists enabled (`[lists] enable = true`). The subscription store is automatically created when the server starts.

## How It Works

When the server receives a message addressed to a mailing list:

1. The server detects the mailbox is a list (it has a `subscribers.txt` file)
2. If the message body is a subscription command (`subscribe`, `confirm`, `unsubscribe`), it is handled immediately and not stored or forwarded
3. Otherwise, the message is forwarded to each subscriber
4. The server uses an auto-generated identity certificate for the list when forwarding
5. If `archive = true`, a copy of the message is stored in the list's mailbox directory

## The Subscribers File

The `subscribers.txt` file contains one address per line (`mailbox@hostname`). Lines starting with `#` are comments and blank lines are ignored:

```
# Development announcements
alice@example.com
bob@remote.host
carol@another.host
```

You can edit this file manually — changes take effect on the next incoming message without a server restart.

## Loop Prevention

The server prevents forwarding loops by checking if the list address already appears in the message's recipient list. If it does, the message is not forwarded again.

## Address Verification

When adding subscribers via `list add` (without `--no-verify`) or via self-service `subscribe`, the server requires address verification:

1. A 6-character hex token is generated and stored in `subscription_pending.db` (SQLite, alongside the mailbox directory)
2. A confirmation message is sent to the subscriber's address using the list's identity certificate
3. The subscriber replies with `confirm <TOKEN>` to complete the subscription
4. Tokens expire after 24 hours

Pending subscriptions are visible in `list subscribers` output with a `[pending]` tag. The `list remove` command also cleans up any pending entries.

## Directory Structure

A mailing list mailbox looks like:

```
mailboxes/
  subscription_pending.db               <- pending subscription tokens (SQLite)
  dev-announce/
    subscribers.txt                      <- subscriber list (marker file)
    .list-identity.crt                   <- auto-generated list identity cert
    .list-identity.key                   <- auto-generated list identity key
    20260211T120000Z-a1b2c3d4.gemmail    <- archived message (if archive=true)
```

## Full Example

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
mailbox_dir = "/var/mail/misfin"

[lists]
enable = true
archive = true
```

Then create the list and add subscribers:

```bash
titlani list create dev-announce -d /var/mail/misfin
titlani list add dev-announce alice@example.com -H mail.example.com
titlani list add dev-announce bob@remote.host -H mail.example.com
```

Subscribers will receive a confirmation token and must reply with `confirm <TOKEN>` before they can post. Once confirmed, messages sent to `dev-announce@mail.example.com` will be forwarded to all subscribers.
