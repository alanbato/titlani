# Changelog

## Unreleased

- Added `init` wizard — interactive command that generates server and client config files with feature toggles for GMAP, encryption, verification, auto-reply, rate limiting, and access control
- Added per-mailbox contact blocking — server rejects messages from blocked senders with status 61 (Unauthorized Sender). Manage via `mail block` / `mail unblock` CLI commands or a `.blocked` file in the mailbox directory
- Added unread tracking — server stores new messages with a `.gemmail.new` suffix (`.gemmail.enc.new` for encrypted). `mail list` shows a `NEW` indicator and new message count. `mail read` marks messages as read by removing the `.new` suffix. GMAP sync preserves tags when files are renamed
- Added server-side auto-reply — place a `.auto-reply` file in a mailbox directory to send automatic replies. Includes loop prevention (`[Auto-Reply]` subject detection) and per-sender rate limiting. Enable with `[auto_reply]` in server config
- Added GMAP (Gemini Mailbox Access Protocol) support for remote mailbox access on a separate port
    - Message retrieval (`/msgid/<id>`), tag management (`/tag/`, `/untag/`), and deletion (`/delete`)
    - Per-mailbox JSON index (`.gmap.json`) with auto-tagging (Inbox, Unread) and filesystem sync
    - Separate TLS context with client certificate authentication using Misfin identity certs
    - Enable with `[gmap] enable = true` in server config
- Added mailing list support — server forwards messages to all subscribers when a mailbox contains `subscribers.txt`. CLI commands: `list create`, `list subscribers`, `list add`, `list remove`. Enable with `[lists]` in server config
- Added self-service mailing list subscription — users can send `subscribe`, `confirm <TOKEN>`, or `unsubscribe` as the message body to a list address. Command messages are intercepted before the subscriber-only posting check and are never stored or forwarded
- Added address verification for mailing list subscriptions — `list add` now sends a confirmation token by default (use `--no-verify` to skip). Pending tokens are stored in a SQLite database (`subscription_pending.db`) with 24-hour expiry. `list subscribers` shows `[confirmed]` vs `[pending]` status. `list remove` also cleans up pending entries
- Added SPKI-based sender verification as an alternative to probe-based verification. Uses a TOFU model for server TLS certificate public key hashes. Configure with `method = "spki"` in `[verification]`
- Added `verification spki list` and `verification spki clear` CLI commands for managing the server SPKI cache
- Added `mail search` command with per-field filters (`--from`, `--subject`, `--body`) and encrypted message support
- Added `mail delete` support for message indices in addition to file paths
- Added `admin fixperms` command to audit and fix mailbox directory permissions
- Added `identity generate --install` flag to register certificates for GMAP authentication and create the mailbox subdirectory
- Added `identity_cert_dir` server config field for per-mailbox identity certificates used by GMAP
- Added OS-user-based mailbox isolation — `mail` commands verify the current user owns the mailbox directory
- `mail list` no longer requires a directory argument — auto-detects from client config (`~/.config/titlani/config.toml`) and mailbox name from `$USER`
- `mail read` accepts a message index (e.g., `titlani mail read 2`) in addition to file paths, using the same ordering as `mail list`
- `mail list` output now includes a `#` index column for easy reference
- Added client configuration file support (`[mail] mailbox_dir`) at the XDG config path
- New `--mailbox-dir` / `-d` option on `mail read` for index resolution

## v0.1.0

*Initial release.*

- Misfin(C) wire protocol implementation (request/response parsing, status codes)
- Gemmail message format (addresses, timestamps, gemtext body)
- Identity certificate generation with Misfin-specific layout (USER_ID, CN, SAN DNS)
- Async client with TOFU support, redirect handling, and context manager
- Async server with two-phase buffering, file-based mailbox storage, and TOML config
- Middleware support via tlacacoca: rate limiting (token bucket) and access control (allow/deny lists)
- CLI commands: `send`, `serve`, `identity generate/info`, `tofu list/revoke`, `version`
