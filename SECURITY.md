# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Titlani, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email **dev@alanbato.com** with:

- A description of the vulnerability
- Steps to reproduce it
- The potential impact
- Any suggested fix (optional)

You should receive an acknowledgment within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Security Model

Titlani implements the Misfin(C) mail transport protocol with mandatory TLS, self-signed identity certificates, and Trust-On-First-Use (TOFU) validation.

For a detailed description of the security model, including threat analysis and cryptographic design, see the [Security Model documentation](https://titlani.readthedocs.io/explanation/security-model/).

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Scope

The following are in scope for security reports:

- TLS configuration weaknesses
- Cryptographic implementation issues (at-rest encryption, key derivation)
- Path traversal or injection in mailbox handling
- Authentication or authorization bypasses
- Denial of service beyond documented protocol limits

The following are **out of scope** (known protocol-level limitations documented in the security model):

- Lack of TLS client certificate verification (OpenSSL 3.x limitation)
- TOFU vulnerability on first connection
- Self-reported sender identity in gemmail metadata
