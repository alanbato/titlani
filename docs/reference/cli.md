# CLI Commands

Titlani provides the `titlani` command-line tool for sending messages, running servers, and managing identities.

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
titlani mail list <mailbox_dir> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `mailbox_dir` | Path to mailbox directory |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--mailbox` | `-m` | — | Filter by specific mailbox name |

Encrypted messages (`.gemmail.enc`) are shown with an encrypted indicator.

---

## `mail read`

Read and display a gemmail message.

```bash
titlani mail read <gemmail_file> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `gemmail_file` | Path to `.gemmail` or `.gemmail.enc` file |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--encryption-key` | `-e` | — | Path to X25519 private key for decryption |

For `.gemmail.enc` files, the CLI auto-discovers `<mailbox>.enc.key` from the mailbox parent directory. Use `--encryption-key` to override.

**Example:**

```bash
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
