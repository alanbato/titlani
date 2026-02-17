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

Add subscribers:

```bash
titlani list add dev-announce alice@example.com
titlani list add dev-announce bob@remote.host
```

View subscribers:

```bash
titlani list subscribers dev-announce
```

Remove a subscriber:

```bash
titlani list remove dev-announce alice@example.com
```

## How It Works

When the server receives a message addressed to a mailing list:

1. The server detects the mailbox is a list (it has a `subscribers.txt` file)
2. The message is forwarded to each subscriber
3. The server uses an auto-generated identity certificate for the list when forwarding
4. If `archive = true`, a copy of the message is stored in the list's mailbox directory

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

## Directory Structure

A mailing list mailbox looks like:

```
mailboxes/
  dev-announce/
    subscribers.txt                   <- subscriber list (marker file)
    .list-identity.crt                <- auto-generated list identity cert
    .list-identity.key                <- auto-generated list identity key
    20260211T120000Z-a1b2c3d4.gemmail <- archived message (if archive=true)
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
titlani list add dev-announce alice@example.com
titlani list add dev-announce bob@remote.host
```

Messages sent to `dev-announce@mail.example.com` will be forwarded to all subscribers.
