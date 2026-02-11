# Changelog

## Unreleased

- Added GMAP (Gemini Mailbox Access Protocol) support for remote mailbox access over Gemini protocol on the same port as Misfin
    - Message retrieval (`/msgid/<id>`), tag management (`/tag/`, `/untag/`), and deletion (`/delete`)
    - Per-mailbox JSON index (`.gmap.json`) with auto-tagging (Inbox, Unread) and filesystem sync
    - Protocol multiplexer detects `gemini://` vs `misfin://` from first bytes
    - Client certificate authentication using Misfin identity certs
    - Enable with `[gmap] enable = true` in server config
- `mail list` no longer requires a directory argument — auto-detects from client config (`~/.config/titlani/config.toml`) and defaults `--mailbox` to `$USER`
- `mail read` accepts a message index (e.g., `titlani mail read 2`) in addition to file paths, using the same ordering as `mail list`
- `mail list` output now includes a `#` index column for easy reference
- Added client configuration file support (`[mail] mailbox_dir`) at the XDG config path
- New `--mailbox-dir` / `-d` and `--mailbox` / `-m` options on `mail read` for index resolution

## v0.1.0

*Initial release.*

- Misfin(C) wire protocol implementation (request/response parsing, status codes)
- Gemmail message format (addresses, timestamps, gemtext body)
- Identity certificate generation with Misfin-specific layout (USER_ID, CN, SAN DNS)
- Async client with TOFU support, redirect handling, and context manager
- Async server with two-phase buffering, file-based mailbox storage, and TOML config
- Middleware support via tlacacoca: rate limiting (token bucket) and access control (allow/deny lists)
- CLI commands: `send`, `serve`, `identity generate/info`, `tofu list/revoke`, `version`
