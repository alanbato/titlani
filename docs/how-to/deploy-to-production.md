# Deploy to Production

This guide covers end-to-end deployment of a Titlani Misfin mail server. Pick the section that matches your setup.

## Overview

| Deployment style | Service file | Audience |
|---|---|---|
| **Single-user (systemd)** | `titlani.service` | Personal server, one mailbox |
| **Multi-user (systemd, hardened)** | `titlani-hardened.service` | Shared server, multiple mailboxes |
| **Docker** | `docker-compose.yml` | Container-based hosting |

## Single-user deployment (systemd)

### 1. Install Titlani

```bash
# Using uv (recommended)
uv tool install titlani

# Or using pipx
pipx install titlani
```

### 2. Find the binary path

```bash
which titlani
# e.g. /home/you/.local/bin/titlani
```

You will need this path for the service file.

### 3. Create a system user and directories

```bash
sudo useradd --system --shell /usr/sbin/nologin titlani
sudo mkdir -p /etc/titlani /var/lib/titlani/mailboxes
sudo chown -R titlani:titlani /var/lib/titlani
```

### 4. Configure the server

Copy the example config and edit it:

```bash
sudo cp contrib/config.systemd.toml /etc/titlani/server.toml
sudo $EDITOR /etc/titlani/server.toml
```

At minimum, set `hostname` to your public domain:

```toml
[server]
hostname = "mail.example.com"
host = "0.0.0.0"
port = 1958
mailbox_dir = "/var/lib/titlani/mailboxes"
certfile = "/etc/titlani/server.pem"
keyfile = "/etc/titlani/server.key"
identity_certfile = "/etc/titlani/identity.pem"
identity_keyfile = "/etc/titlani/identity.key"
```

!!! tip
    Certificates are auto-generated on first start if the configured paths don't exist yet. This means you can skip manual cert generation — just make sure the `titlani` user can write to `/etc/titlani/`.

### 5. Install and start the service

```bash
# Copy the service file and update the ExecStart path
sudo cp contrib/titlani.service /etc/systemd/system/
sudo sed -i "s|/usr/local/bin/titlani|$(which titlani)|" /etc/systemd/system/titlani.service

sudo systemctl daemon-reload
sudo systemctl enable --now titlani
sudo systemctl status titlani
```

### 6. Create your mailbox

```bash
sudo -u titlani mkdir -p /var/lib/titlani/mailboxes/alice
sudo -u titlani chmod 700 /var/lib/titlani/mailboxes/alice
```

### 7. Set up client config for reading mail

On the same machine (or any machine that can read the server config):

```bash
mkdir -p ~/.config/titlani
cat > ~/.config/titlani/config.toml << 'EOF'
[mail]
server_config = "/etc/titlani/server.toml"
EOF
```

Or run the interactive wizard:

```bash
titlani init
```

Now you can read mail:

```bash
titlani mail list -m alice
titlani mail read 1 -m alice
```

## Multi-user deployment (systemd, hardened)

The hardened variant adds kernel and filesystem protections on top of the single-user setup.

### Differences from single-user

1. **Use the hardened service file:**

    ```bash
    sudo cp contrib/titlani-hardened.service /etc/systemd/system/titlani.service
    ```

2. **Per-mailbox identity certificates:** Generate a separate identity cert for each user so replies carry the correct fingerprint:

    ```bash
    titlani identity generate alice mail.example.com --install /etc/titlani/certs/
    titlani identity generate bob mail.example.com --install /etc/titlani/certs/
    ```

    Point the server config at the cert directory:

    ```toml
    [server]
    identity_cert_dir = "/etc/titlani/certs"
    ```

3. **Encryption key management:** Enable at-rest encryption so only each user can read their own mail:

    ```toml
    [encryption]
    enable = true
    key_dir = "/etc/titlani/keys"
    ```

    Generate encryption keys per mailbox:

    ```bash
    titlani identity generate alice mail.example.com --with-encryption-key
    ```

    Place `.enc.pub` files in `key_dir` and give `.enc.key` files to each user (mode `0600`).

## Docker deployment

The `contrib/` directory contains ready-to-use Docker files.

```bash
cd contrib/
# Edit config.docker.toml with your hostname, then:
docker compose up -d
```

The `docker-compose.yml` mounts:

- `config.docker.toml` → `/etc/titlani/server.toml`
- A `certs` volume → `/etc/titlani/certs/`
- A `mailboxes` volume → `/var/lib/titlani/mailboxes`

To use pre-generated certificates, copy them into the `certs` volume before starting.

## Client config setup

The CLI commands (`mail list`, `mail read`, etc.) need to know where the mailbox directory is. There are three ways to configure this:

1. **Client config file** (recommended): Create `~/.config/titlani/config.toml` pointing at the server config:

    ```toml
    [mail]
    server_config = "/etc/titlani/server.toml"
    ```

2. **Interactive wizard**: Run `titlani init` which generates both server and client configs.

3. **Explicit path**: Pass `--mailbox-dir /var/lib/titlani/mailboxes` on each command.

If you are running as root or a different user than the mailbox owner, use the `--mailbox` / `-m` flag:

```bash
titlani mail list -m alice
```

## Troubleshooting

### Port is open but clients can't connect

Misfin uses TLS on port 1958 (not HTTP). Services like Cloudflare that only proxy HTTP/HTTPS traffic will not work — you need a direct TCP connection. If you're behind such a proxy, either bypass it for port 1958 or use a different hosting setup.

Also check your firewall:

```bash
# iptables
sudo iptables -L -n | grep 1958

# nftables
sudo nft list ruleset | grep 1958
```

### Permission denied on cert files

Make sure the `titlani` system user owns the certificate files:

```bash
sudo chown titlani:titlani /etc/titlani/*.pem /etc/titlani/*.key
sudo chmod 600 /etc/titlani/*.key
```

### `$USER` not set / wrong mailbox name

When running mail commands as root or via `sudo`, `$USER` may be `root` instead of the mailbox name. Use the `--mailbox` flag:

```bash
titlani mail list -m alice
```

### TOFU breaks on restart (ephemeral certs)

If clients see `CertificateChangedError` after a server restart, the server was generating temporary certificates that didn't persist. Fix this by setting explicit cert paths in `server.toml`:

```toml
[server]
certfile = "/etc/titlani/server.pem"
keyfile = "/etc/titlani/server.key"
```

Certificates are auto-generated at these paths on first start and reused on subsequent runs.

### `localhost` vs `0.0.0.0` bind address

- `host = "localhost"` — only accepts connections from the local machine
- `host = "0.0.0.0"` — accepts connections from any network interface

For a public server, use `0.0.0.0`. The `titlani init` wizard defaults to `0.0.0.0` when the hostname is not `localhost`.
