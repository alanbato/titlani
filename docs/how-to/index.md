# How-To Guides

Practical recipes for common tasks. Each guide focuses on a single goal and assumes you already have Titlani installed.

<div class="grid cards" markdown>

-   :material-card-account-details:{ .lg .middle } **Generate Identities**

    ---

    Create and inspect Misfin identity certificates via CLI or Python.

    [:octicons-arrow-right-24: Guide](generate-identities.md)

-   :material-cog:{ .lg .middle } **Configure Server**

    ---

    Write a TOML config file, set CLI overrides, and manage auto-generated certs.

    [:octicons-arrow-right-24: Guide](configure-server.md)

-   :material-shield-check:{ .lg .middle } **Manage TOFU**

    ---

    List, revoke, and programmatically manage the Trust-On-First-Use database.

    [:octicons-arrow-right-24: Guide](manage-tofu.md)

-   :material-speedometer:{ .lg .middle } **Rate Limiting**

    ---

    Configure token bucket rate limiting to protect your server.

    [:octicons-arrow-right-24: Guide](rate-limiting.md)

-   :material-lock:{ .lg .middle } **Access Control**

    ---

    Set up IP allow/deny lists for your server.

    [:octicons-arrow-right-24: Guide](access-control.md)

-   :material-account-check:{ .lg .middle } **Sender Verification**

    ---

    Verify that senders actually exist on their claimed server.

    [:octicons-arrow-right-24: Guide](sender-verification.md)

-   :material-lock-outline:{ .lg .middle } **At-Rest Encryption**

    ---

    Encrypt stored messages with per-mailbox X25519 keys.

    [:octicons-arrow-right-24: Guide](at-rest-encryption.md)

-   :material-puzzle:{ .lg .middle } **Custom Message Handler**

    ---

    Subclass `MessageHandler` to implement custom delivery logic.

    [:octicons-arrow-right-24: Guide](custom-message-handler.md)

-   :material-email-edit:{ .lg .middle } **Compose Gemmail**

    ---

    Build, parse, and serialize gemmail messages programmatically.

    [:octicons-arrow-right-24: Guide](compose-gemmail.md)

</div>
