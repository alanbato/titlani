# Access Control

The Titlani server supports IP-based access control via tlacacoca's `AccessControl` middleware.

## Enable in Config

Add an `[access_control]` section to your TOML config:

```toml
[access_control]
enable = true
allow_list = ["192.168.1.0/24", "10.0.0.0/8"]
deny_list = []
default_allow = true
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable` | bool | `false` | Enable access control |
| `allow_list` | list[str] | `[]` | IPs/CIDRs to always allow |
| `deny_list` | list[str] | `[]` | IPs/CIDRs to always deny |
| `default_allow` | bool | `true` | Allow IPs not in either list |

## Modes

### Allowlist Mode (Whitelist)

Only allow specific IPs, deny everything else:

```toml
[access_control]
enable = true
allow_list = ["192.168.1.0/24", "10.0.0.5"]
deny_list = []
default_allow = false
```

### Denylist Mode (Blacklist)

Allow everything except specific IPs:

```toml
[access_control]
enable = true
allow_list = []
deny_list = ["203.0.113.0/24", "198.51.100.42"]
default_allow = true
```

### Combined

Allow list takes priority over deny list:

```toml
[access_control]
enable = true
allow_list = ["10.0.0.5"]
deny_list = ["10.0.0.0/8"]
default_allow = true
```

In this example, `10.0.0.5` is allowed (explicit allow), all other `10.0.0.0/8` addresses are denied, and everything else is allowed (default).

## Denied Client Behavior

When access is denied, the server responds with status **53** (domain not serviced), closing the connection.
