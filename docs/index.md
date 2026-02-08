# Titlani

**Misfin(C) mail protocol client and server library for Python.**

Titlani is a complete implementation of the [Misfin(C)](https://misfin.org/) mail transport protocol — a lightweight, privacy-focused mail protocol influenced by Gemini that uses mandatory TLS with self-signed identity certificates and Trust-On-First-Use (TOFU) validation.

---

<div class="grid cards" markdown>

-   :material-email-fast:{ .lg .middle } **Protocol**

    ---

    Full Misfin(C) wire format implementation with request/response parsing, status codes, and size limits.

-   :material-card-account-details:{ .lg .middle } **Identity**

    ---

    Generate and manage Misfin identity certificates with custom layouts (USER_ID, CN, SAN DNS).

-   :material-shield-lock:{ .lg .middle } **TOFU**

    ---

    Built-in Trust-On-First-Use certificate validation with persistent database and revocation support.

-   :material-lightning-bolt:{ .lg .middle } **Asyncio**

    ---

    Fully async client and server built on `asyncio.Protocol` with middleware, rate limiting, and access control.

</div>

---

## Quick Example

=== "Send a message"

    ```bash
    # Generate an identity
    titlani identity generate alice example.com --blurb "Alice Smith"

    # Send a message
    titlani send bob@remote.host "Hello from Misfin!" \
        --cert alice.pem --key alice.key --subject "Greetings"
    ```

=== "Start a server"

    ```bash
    # Start with defaults (auto-generates certs)
    titlani serve --hostname example.com --mailbox-dir ./mailboxes

    # Or use a config file
    titlani serve --config server.toml
    ```

=== "Python API"

    ```python
    from titlani import MisfinClient, MisfinAddress

    async with MisfinClient(
        client_cert="alice.pem",
        client_key="alice.key",
    ) as client:
        response = await client.send(
            to="bob@remote.host",
            body="Hello from Misfin!",
            subject="Greetings",
        )
        print(f"{response.status} {response.meta}")
    ```

---

## Install

```bash
uv add titlani
```

Or with pip:

```bash
pip install titlani
```

See the [Installation](installation.md) guide for more options.

---

## Learn More

<div class="grid cards" markdown>

-   [**Tutorials**](tutorials/index.md) — Step-by-step lessons for getting started
-   [**How-To Guides**](how-to/index.md) — Recipes for specific tasks
-   [**Reference**](reference/index.md) — API, CLI, and configuration details
-   [**Explanation**](explanation/index.md) — Background and design decisions

</div>
