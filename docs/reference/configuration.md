# Configuration

The Titlani server is configured via a TOML file with three sections.

## `[server]`

Core server settings.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | string | `"localhost"` | Bind address |
| `port` | int | `1958` | Listen port (must be 1-65535) |
| `hostname` | string | `"localhost"` | Hostname for mail routing (must match recipient addresses) |
| `certfile` | string | — | Path to TLS certificate PEM file |
| `keyfile` | string | — | Path to TLS private key PEM file |
| `mailbox_dir` | string | `"mailboxes"` | Directory containing mailbox subdirectories |
| `identity_certfile` | string | — | Path to server identity certificate |
| `identity_keyfile` | string | — | Path to server identity private key |

!!! note
    If `certfile`/`keyfile` are omitted, temporary TLS certificates are auto-generated.
    If `identity_certfile`/`identity_keyfile` are omitted, a temporary identity for `postmaster@<hostname>` is auto-generated.

## `[rate_limit]`

Token bucket rate limiting per client IP.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable` | bool | `false` | Enable rate limiting |
| `capacity` | int | `10` | Maximum tokens in bucket |
| `refill_rate` | float | `1.0` | Tokens added per second |
| `retry_after` | int | `30` | Suggested retry delay in seconds (sent in status 44 response) |

## `[access_control]`

IP-based access control.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable` | bool | `false` | Enable access control |
| `allow_list` | list[string] | `[]` | IPs or CIDRs to always allow |
| `deny_list` | list[string] | `[]` | IPs or CIDRs to always deny |
| `default_allow` | bool | `true` | Allow IPs not in either list |

Allow list takes priority over deny list.

## Full Example

```toml
[server]
host = "0.0.0.0"
port = 1958
hostname = "mail.example.com"
certfile = "server.pem"
keyfile = "server.key"
mailbox_dir = "/var/mail/misfin"
identity_certfile = "identity.pem"
identity_keyfile = "identity.key"

[rate_limit]
enable = true
capacity = 20
refill_rate = 2.0
retry_after = 15

[access_control]
enable = true
allow_list = ["192.168.0.0/16"]
deny_list = ["10.0.0.99"]
default_allow = false
```

## Validation

`ServerConfig.validate()` checks:

- Port is between 1 and 65535
- Certificate files exist if specified
- Key files exist if specified
