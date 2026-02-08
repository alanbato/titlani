# Manage TOFU

Trust-On-First-Use (TOFU) stores server certificate fingerprints on first contact and warns if they change. Titlani uses tlacacoca's `TOFUDatabase` for this.

## CLI: List Known Hosts

```bash
titlani tofu list
```

Shows all stored host fingerprints:

```
Hostname       Port  Fingerprint          First Seen           Last Seen
example.com    1958  a1b2c3d4e5f6...      2025-01-01 10:00:00  2025-06-15 14:30:00
remote.host    1958  f6e5d4c3b2a1...      2025-03-10 08:00:00  2025-06-15 14:30:00
```

## CLI: Revoke a Host

Remove a host from the TOFU database (forces re-trust on next connection):

```bash
titlani tofu revoke example.com
titlani tofu revoke example.com --port 1959  # Non-default port
```

## Python: Handle Certificate Changes

When TOFU detects a fingerprint mismatch, it raises `CertificateChangedError`:

```python
from tlacacoca import CertificateChangedError
from titlani import MisfinClient

async with MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
) as client:
    try:
        response = await client.send(to="bob@example.com", body="Hello!")
    except CertificateChangedError as e:
        print(f"Host: {e.hostname}")
        print(f"Expected fingerprint: {e.expected_fingerprint}")
        print(f"Actual fingerprint: {e.actual_fingerprint}")
        # Decide whether to re-trust or abort
```

## Python: Custom TOFU Database Path

```python
from pathlib import Path
from titlani import MisfinClient

client = MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
    tofu_db_path=Path("~/.titlani/known_hosts.db"),
)
```

## Disable TOFU

For testing or environments where TOFU is not desired:

```python
client = MisfinClient(
    client_cert="alice.pem",
    client_key="alice.key",
    trust_on_first_use=False,
)
```

!!! warning
    Disabling TOFU removes man-in-the-middle detection. Only do this for testing.
