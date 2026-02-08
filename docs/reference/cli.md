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

**Output files:**

- `<mailbox>.pem` — Certificate file
- `<mailbox>.key` — Private key file (mode 600)

**Example:**

```bash
titlani identity generate alice example.com \
    --blurb "Alice Smith" --output-dir ./certs
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

## `version`

Display version information.

```bash
titlani version
```
