# CLI Commands

Titlani provides the `titlani` command-line tool for sending messages, running servers, and managing identities.

## `init`

Interactive wizard to generate server and client config files.

```bash
titlani init [OPTIONS]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output-dir` | `-o` | `~/.config/titlani` | Directory to write config files to |
| `--force` | `-f` | `false` | Overwrite existing config files |

The wizard walks through three steps:

1. **Essentials** — hostname, port, mailbox directory
2. **Feature toggles** — GMAP, sender verification, encryption, auto-reply, rate limiting, access control
3. **Feature details** — follow-up prompts for each enabled feature

**Output files:**

- `server.toml` — Server configuration
- `config.toml` — Client configuration (references `server.toml`)

**Example:**

```bash
titlani init
titlani init --output-dir ./config --force
```

---

## `send`

Send a Misfin message.

```bash
titlani send <to> <message> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `to` | Recipient address (`mailbox@hostname`) |
| `message` | Message body text |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--subject` | `-s` | — | Message subject (prepended as `#` heading) |
| `--cert` | — | — | Path to sender identity certificate |
| `--key` | — | — | Path to sender identity private key |
| `--timeout` | `-t` | `30.0` | Request timeout in seconds |

**Example:**

```bash
titlani send bob@example.com "Hello, Bob!" \
    --cert alice.pem --key alice.key \
    --subject "Greetings"
```

---

## `serve`

Start a Misfin server.

```bash
titlani serve [OPTIONS]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | — | Path to TOML config file |
| `--host` | `-h` | `localhost` | Server bind address |
| `--port` | `-p` | `1958` | Server port |
| `--hostname` | — | `localhost` | Hostname for mail routing |
| `--cert` | — | — | Path to TLS certificate |
| `--key` | — | — | Path to TLS private key |
| `--mailbox-dir` | — | `mailboxes` | Directory for mailbox storage |
| `--log-level` | `-l` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

CLI options override values from the config file.

**Example:**

```bash
titlani serve --config server.toml --log-level DEBUG
```

---

## `identity generate`

Generate a Misfin identity certificate.

```bash
titlani identity generate <mailbox> <hostname> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `mailbox` | Mailbox name (e.g., `alice`) |
| `hostname` | Hostname (e.g., `example.com`) |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--blurb` | `-b` | `""` | Human-readable description |
| `--output-dir` | `-o` | `.` | Output directory |
| `--valid-days` | — | `365` | Certificate validity in days |
| `--key-size` | — | `2048` | RSA key size in bits |
| `--with-encryption-key` | — | `false` | Also generate X25519 keypair for at-rest encryption |

**Output files:**

- `<mailbox>.pem` — Certificate file
- `<mailbox>.key` — Private key file (mode 600)
- `<mailbox>.enc.pub` — Encryption public key (only with `--with-encryption-key`)
- `<mailbox>.enc.key` — Encryption private key, mode 600 (only with `--with-encryption-key`)

**Example:**

```bash
titlani identity generate alice example.com \
    --blurb "Alice Smith" --output-dir ./certs \
    --with-encryption-key
```

---

## `identity info`

Display identity information from a certificate file.

```bash
titlani identity info <cert_file>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `cert_file` | Path to certificate file |

**Output fields:** Address, Blurb, Hostname, Fingerprint, Not Before, Not After.

---

## `tofu list`

List all hosts in the TOFU database.

```bash
titlani tofu list
```

**Output columns:** Hostname, Port, Fingerprint, First Seen, Last Seen.

---

## `tofu revoke`

Remove a host from the TOFU database.

```bash
titlani tofu revoke <hostname> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `hostname` | Hostname to revoke |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--port` | `-p` | `1958` | Port number |

---

## `mail list`

List messages in a mailbox directory.

```bash
titlani mail list [mailbox_dir] [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `mailbox_dir` | Path to mailbox directory (optional — auto-detected from [client config](configuration.md#client-configuration) if omitted) |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--mailbox` | `-m` | `$USER` | Filter by specific mailbox name (defaults to current OS user) |

Messages are listed newest-first with a `#` index column. You can pass the index number to `mail read` to open a message directly.

Unread messages (`.gemmail.new`) are shown with a `NEW` indicator. The table title includes a count of new messages (e.g., "Messages (5) (2 new)").

Encrypted messages (`.gemmail.enc`) are shown with an encrypted indicator.

**Examples:**

```bash
# Auto-detect mailbox directory from config, mailbox from $USER
titlani mail list

# Explicit directory, auto-detect mailbox
titlani mail list /var/mail/misfin

# Explicit directory and mailbox
titlani mail list /var/mail/misfin --mailbox alice
```

---

## `mail read`

Read and display a gemmail message. Accepts either a message index (from `mail list`) or a file path.

```bash
titlani mail read <message> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `message` | Message index (from `mail list` output) or path to `.gemmail`/`.gemmail.enc` file |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--mailbox-dir` | `-d` | — | Mailbox directory for index resolution (auto-detected from [client config](configuration.md#client-configuration) if omitted) |
| `--mailbox` | `-m` | `$USER` | Mailbox name for index resolution (defaults to current OS user) |
| `--encryption-key` | `-e` | — | Path to X25519 private key for decryption |

When using an index, the mailbox directory and name are resolved the same way as `mail list` — from explicit options, then client config, then `$USER`.

Reading an unread message (`.gemmail.new`) automatically marks it as read by renaming it to `.gemmail`. This happens after the message is displayed.

For `.gemmail.enc` files, the CLI auto-discovers `<mailbox>.enc.key` from the mailbox parent directory. Use `--encryption-key` to override.

**Examples:**

```bash
# Read message #2 from the listing (uses config + $USER)
titlani mail read 2

# Read by index with explicit directory and mailbox
titlani mail read 1 -d /var/mail/misfin -m alice

# Read by file path (still works)
titlani mail read mailboxes/alice/message.gemmail.enc \
    --encryption-key ~/.titlani/alice.enc.key
```

---

## `mail reply`

Reply to a gemmail message.

```bash
titlani mail reply <gemmail_file> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `gemmail_file` | Path to `.gemmail` or `.gemmail.enc` file to reply to |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--message` | `-m` | — | Reply message body (opens `$EDITOR` if omitted) |
| `--quote` | `-q` | `false` | Quote original message with `>` prefix |
| `--cert` | — | — | Path to sender identity certificate |
| `--key` | — | — | Path to sender identity private key |
| `--encryption-key` | `-e` | — | Path to X25519 private key for decryption |
| `--timeout` | `-t` | `30.0` | Request timeout in seconds |

**Example:**

```bash
titlani mail reply mailboxes/alice/message.gemmail.enc \
    --encryption-key ~/.titlani/alice.enc.key \
    --cert alice.pem --key alice.key \
    --message "Thanks for your message!"
```

---

## `mail block`

Block a sender address from delivering mail to a mailbox.

```bash
titlani mail block <address> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `address` | Sender address to block (`mailbox@hostname`) |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--mailbox-dir` | `-d` | — | Mailbox directory (auto-detected from [client config](configuration.md#client-configuration) if omitted) |
| `--mailbox` | `-m` | `$USER` | Mailbox name |

**Example:**

```bash
titlani mail block spam@evil.com --mailbox alice
```

See [Contact Blocking](../how-to/contact-blocking.md) for details.

---

## `mail unblock`

Remove a sender address from the block list.

```bash
titlani mail unblock <address> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `address` | Sender address to unblock |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--mailbox-dir` | `-d` | — | Mailbox directory (auto-detected from [client config](configuration.md#client-configuration) if omitted) |
| `--mailbox` | `-m` | `$USER` | Mailbox name |

**Example:**

```bash
titlani mail unblock spam@evil.com --mailbox alice
```

---

## `mail delete`

Delete one or more stored messages.

```bash
titlani mail delete <files...> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `files` | Paths to `.gemmail` or `.gemmail.enc` files to delete |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--force` | `-f` | `false` | Skip confirmation prompt |

---

## `verification list`

List all verified senders.

```bash
titlani verification list [OPTIONS]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--cache` | `-c` | — | Path to verification cache database |

---

## `version`

Display version information.

```bash
titlani version
```
