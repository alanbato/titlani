# Changelog

## v0.1.0

*Initial release.*

- Misfin(C) wire protocol implementation (request/response parsing, status codes)
- Gemmail message format (addresses, timestamps, gemtext body)
- Identity certificate generation with Misfin-specific layout (USER_ID, CN, SAN DNS)
- Async client with TOFU support, redirect handling, and context manager
- Async server with two-phase buffering, file-based mailbox storage, and TOML config
- Middleware support via tlacacoca: rate limiting (token bucket) and access control (allow/deny lists)
- CLI commands: `send`, `serve`, `identity generate/info`, `tofu list/revoke`, `version`
