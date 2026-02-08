# Configure Server

The Titlani server is configured via a TOML file, with CLI flags as overrides.

## Create a Config File

Create `server.toml` with the `[server]` section:

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
certfile = "server.pem"
keyfile = "server.key"
mailbox_dir = "mailboxes"
identity_certfile = "identity.pem"
identity_keyfile = "identity.key"
```

Start the server:

```bash
titlani serve --config server.toml
```

## CLI Overrides

CLI flags override config file values:

```bash
titlani serve --config server.toml \
    --host 127.0.0.1 \
    --port 1959 \
    --log-level DEBUG
```

## Auto-Generated Certificates

If `certfile`/`keyfile` are not specified, the server auto-generates temporary TLS certificates using `tlacacoca.generate_self_signed_cert()`.

If `identity_certfile`/`identity_keyfile` are not specified, the server auto-generates a temporary identity certificate for `postmaster@<hostname>`.

!!! warning
    Auto-generated certificates are created in a temporary directory and are not persisted across server restarts. For production, generate and configure permanent certificates.

## Mailbox Directory Setup

Create a directory for each mailbox you want to receive mail for:

```bash
mkdir -p mailboxes/alice
mkdir -p mailboxes/bob
mkdir -p mailboxes/postmaster
```

Messages to `alice@mail.example.com` are stored as timestamped `.gemmail` files in `mailboxes/alice/`.

If a message is sent to a mailbox that doesn't have a corresponding directory, the server responds with status **51** (mailbox not found).

## Full Config Reference

See [Configuration Reference](../reference/configuration.md) for all available options including rate limiting and access control sections.
