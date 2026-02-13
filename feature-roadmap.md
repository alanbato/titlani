# Feature Roadmap

Future features for Titlani, documented with implementation sketches. These are **not currently being implemented** — this document exists for planning and discussion.

---

~~1. Contact/Sender Blocking~~ — DONE

**Description**: Allow server operators to configure per-mailbox deny-lists that reject messages from specific senders with status 61 (Unauthorized Sender).

**Status**: Implemented. Per-mailbox `.blocked` file (one address per line, case-insensitive matching). Server checks both cert-based and gemmail metadata senders before delivery, returning status 61 (Unauthorized Sender) on match. CLI `mail block <address>` / `mail unblock <address>` commands manage the block list. Unblocking the last address removes the `.blocked` file.

---

~~2. Unread Tracking~~ — DONE

**Description**: Track which messages have been read using a `.gemmail.new` suffix convention. Messages arrive as `.gemmail.new` and are renamed to `.gemmail` when read.

**Status**: Implemented. Server stores new messages as `.gemmail.new` (and `.gemmail.enc.new` for encrypted). `mail list` shows `NEW` indicator per message and "(N new)" count in the table title. `mail read` marks messages as read by renaming `.gemmail.new` → `.gemmail`. All four suffix variants (`.gemmail`, `.gemmail.new`, `.gemmail.enc`, `.gemmail.enc.new`) handled consistently across CLI listing, display, and GMAP sync. GMAP preserves existing tags when a file is renamed by the CLI.

---

## 3. Message Search

**Description**: Add a `mail search` CLI command that searches through gemmail files by sender, subject, or body text.

**Why it matters**: Skylab has search functionality. As mailboxes grow, finding specific messages becomes essential.

**Other implementations**: Skylab supports search through its Gemini frontend.

**Approach**:
- Add `mail search <query>` command
- Iterate over gemmail files in the mailbox, parse each, match query against sender addresses, subject (`#` heading), and body text
- Support flags: `--from <addr>`, `--subject <text>`, `--body <text>`, `--all` (default, searches everything)
- Display results in the same table format as `mail list`
- For encrypted files, skip unless `--encryption-key` is provided

**Files touched**: `cli/commands/mail.py`, `cli/mailbox.py`

**Effort**: Medium (3-4 hours)

---

~~4. Out-of-Office Auto-Replies~~ — DONE

**Description**: When a `.auto-reply` file exists in a mailbox directory, the server automatically sends a reply to the sender with the file's contents.

**Status**: Implemented. After successful delivery, server checks for `.auto-reply` file in the recipient's mailbox directory. Sends reply via `MisfinClient` using the server's identity cert/key with `[Auto-Reply]` subject. Loop prevention: messages containing `[Auto-Reply]` in the subject are skipped. Rate limiting: in-memory per-sender cache with configurable interval (default 86400s), eagerly timestamped to prevent duplicate sends from concurrent messages. Fire-and-forget via `asyncio.ensure_future` — auto-reply failures never affect message delivery. Configure with `[auto_reply]` section in `server.toml` (`enable`, `interval`).

---

## ~~5. GMAP Protocol Support~~ — DONE

**Description**: Implement the Gemini Mailbox Access Protocol (GMAP) for remote mailbox access over Gemini, as specified at `gemini://satch.xyz/misfin/gmap.gmi`.

**Status**: Implemented (core scope). Message retrieval, tag management, deletion, and auto-tagging (Inbox/Unread). Protocol multiplexer on port 1958 detects `gemini://` vs `misfin://`. JSON index per mailbox. Client cert authentication. Enable with `[gmap] enable = true`.

**Not yet implemented**: Sent mail forwarding via GMAP address, draft storage, encrypted message retrieval (returns status 40).

---

## ~~6. Message IDs for Threading~~ — DONE

**Description**: Assign unique message IDs to enable threading and conversation tracking.

**Status**: Implemented. Message IDs are 8-character lowercase hex strings derived from SHA-256 of `sender:timestamp` (with microsecond precision). IDs are embedded in filenames: `YYYYMMDDTHHMMSSZ-<8hex>.gemmail[.enc][.new]`. Backward compatible with old `YYYYMMDDTHHMMSSZ.gemmail` filenames. Threading uses gemtext link convention: `=> mid:<message-id> In reply to` appended to reply bodies by `mail reply`. `mail list` shows reply count indicators `(↳N)` by parsing these links from message bodies. Encrypted messages degrade gracefully (no threading info available without decryption). Core utilities in `content/message_id.py`.

**Not yet implemented**: Conversation grouping/indentation in `mail list`, GMAP-level threading queries, sent mail tracking for full conversation reconstruction.

---

## 7. SMTP Bridge

**Description**: Bridge Misfin messages to/from traditional email via SMTP, allowing Misfin users to communicate with email users.

**Why it matters**: cipres/misfin already has this. It dramatically expands the reach of a Misfin deployment by connecting it to the existing email ecosystem.

**Other implementations**: cipres/misfin has a full SMTP bridge implementation.

**Approach**:
- Inbound (Email → Misfin): Run a lightweight SMTP server (using `aiosmtpd`) that converts incoming emails to gemmail format and stores them in mailbox directories
- Outbound (Misfin → Email): When a recipient address looks like `user@email-domain` (not a known Misfin server), format the gemmail as a plain-text email and send via configured SMTP relay
- Configuration: SMTP relay host/port/auth, domain mapping (which domains are Misfin vs email)
- Header mapping: email Subject → gemmail `#` heading, From/To → sender/recipient lines, Date → timestamp

**Files touched**: New `bridge/` module (`smtp_server.py`, `smtp_client.py`, `converter.py`), `server/config.py` (bridge settings)

**Effort**: High (2-3 days) — SMTP is complex, needs careful security review

---

## ~~8. Mailing List Support~~ — DONE

**Description**: Server acts as a forwarding client, distributing messages sent to a list address to all subscribers.

**Status**: Implemented (core scope). Convention-based detection via `subscribers.txt` marker file in a regular mailbox directory. Subscribers-only posting (non-subscribers rejected with status 61). Loop prevention checks for list address in recipients (rejected with status 59). Auto-generated per-list identity certs (`.list-identity.crt/.key`). Archive + forward mode (configurable via `[lists] archive`). Fire-and-forget async forwarding using `MisfinClient` with list identity cert. CLI commands: `mail list-create`, `mail list-subscribers`, `mail list-add`, `mail list-remove`. Enable with `[lists] enable = true` in `server.toml`.

**Not yet implemented**: Moderation (queued messages requiring approval), per-list config overrides via `[lists.<name>]` sections, sent mail tracking for conversation reconstruction, GMAP-level list archive access.

---

## ~~9. SPKI-Based Sender Verification~~ DONE

**Description**: Verify senders by connecting to their server and caching the Subject Public Key Info (SPKI) from its TLS certificate, then verifying that subsequent messages from that server are signed by the same key. This is Estampa's approach.

**Why it matters**: This is cryptographically stronger than Titlani's current probe-based verification. It verifies the server's identity at the certificate level rather than just confirming mailbox existence.

**Other implementations**: Estampa implements this with `.spki` file caching in its `store/trust/` directory.

**Approach**:
- Add a new verification mode: `verification_mode = "spki"` alongside existing `"off"` / `"optional"` / `"required"`
- On first message from a new server: connect to the sender's server (port 1958), extract the TLS certificate's SPKI (Subject Public Key Info), cache it
- On subsequent messages: extract the connecting client's certificate SPKI and compare against cached value
- Storage: `verification_cache/spki/<hostname>.spki` files (or extend the SQLite cache with an `spki` column)
- Handle key rotation: if SPKI changes, treat like TOFU certificate change — alert or reject depending on configuration
- Could coexist with probe-based verification as a combined mode

**Files touched**: `verification/spki_verifier.py` (new), `verification/cache.py` (SPKI column), `server/config.py`, `server/server.py`

**Effort**: Medium (4-6 hours) — TLS cert extraction is straightforward with `cryptography`
