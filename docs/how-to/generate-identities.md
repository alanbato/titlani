# Generate Identities

Misfin identity certificates identify participants in the protocol. They use a custom certificate layout where the mailbox is stored in the USER_ID field, the blurb in Common Name, and the hostname in a SAN DNS entry.

## CLI: Generate a Certificate

```bash
titlani identity generate alice example.com \
    --blurb "Alice Smith" \
    --valid-days 365 \
    --key-size 2048 \
    --output-dir ./certs
```

This creates `certs/alice.pem` (certificate) and `certs/alice.key` (private key with 600 permissions).

## CLI: Inspect a Certificate

```bash
titlani identity info alice.pem
```

Output:

```
Address:     alice@example.com
Blurb:       Alice Smith
Hostname:    example.com
Fingerprint: a1b2c3d4e5f6...
Not Before:  2025-01-01 00:00:00
Not After:   2026-01-01 00:00:00
```

## Python: Generate a Certificate

```python
from titlani import generate_identity_cert

cert_pem, key_pem = generate_identity_cert(
    mailbox="alice",
    hostname="example.com",
    blurb="Alice Smith",
    key_size=2048,
    valid_days=365,
)

# Write to files
with open("alice.pem", "wb") as f:
    f.write(cert_pem)
with open("alice.key", "wb") as f:
    f.write(key_pem)
```

## Python: Extract Identity from a Certificate

```python
from cryptography.x509 import load_pem_x509_certificate
from titlani import extract_identity

with open("alice.pem", "rb") as f:
    cert = load_pem_x509_certificate(f.read())

identity = extract_identity(cert)
print(identity.mailbox)    # "alice"
print(identity.hostname)   # "example.com"
print(identity.blurb)      # "Alice Smith"
print(identity.address)    # "alice@example.com"
print(identity.long_form)  # "Alice Smith (alice@example.com)"
```

## Python: Normalize Fingerprints

Tlacacoca returns fingerprints in `sha256:hexdigest` format, but Misfin(C) uses plain lowercase hex. Use `normalize_fingerprint()` when crossing the boundary:

```python
from titlani import normalize_fingerprint

# From tlacacoca format
fp = normalize_fingerprint("sha256:A1B2C3D4E5F6...")
# Returns: "a1b2c3d4e5f6..."
```

This function strips known algorithm prefixes (`sha256:`, `sha1:`, `sha512:`, `md5:`), removes non-hex characters, and lowercases the result.
