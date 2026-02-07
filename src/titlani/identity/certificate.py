"""Misfin identity certificate utilities.

Misfin identity certificates use:
- USER_ID: mailbox name
- COMMON_NAME: blurb (human-readable description)
- SAN DNS: hostname
"""

import datetime
import re
from dataclasses import dataclass
from typing import cast

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@dataclass(frozen=True)
class MisfinIdentity:
    mailbox: str
    hostname: str
    blurb: str = ""

    @property
    def address(self) -> str:
        return f"{self.mailbox}@{self.hostname}"

    @property
    def long_form(self) -> str:
        if self.blurb:
            return f"{self.blurb} ({self.address})"
        return self.address


def generate_identity_cert(
    mailbox: str,
    hostname: str,
    blurb: str = "",
    key_size: int = 2048,
    valid_days: int = 365,
) -> tuple[bytes, bytes]:
    """Generate a Misfin identity certificate.

    Uses cryptography directly (not tlacacoca's generate_self_signed_cert)
    because Misfin needs USER_ID for mailbox and CN for blurb, while
    tlacacoca puts hostname in CN.

    Returns:
        Tuple of (certificate_pem, private_key_pem) as bytes.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.USER_ID, mailbox),
            x509.NameAttribute(NameOID.COMMON_NAME, blurb or mailbox),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(days=valid_days)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return cert_pem, key_pem


def extract_identity(cert: x509.Certificate) -> MisfinIdentity:
    """Extract a Misfin identity from a certificate."""
    # Get mailbox from USER_ID
    mailbox = ""
    try:
        attrs = cert.subject.get_attributes_for_oid(NameOID.USER_ID)
        if attrs:
            mailbox = str(attrs[0].value)
    except (IndexError, AttributeError):
        pass

    # Get blurb from COMMON_NAME
    blurb = ""
    try:
        attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if attrs:
            blurb = str(attrs[0].value)
    except (IndexError, AttributeError):
        pass

    # Get hostname from SAN DNS
    hostname = ""
    try:
        san_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san = cast(x509.SubjectAlternativeName, san_ext.value)
        dns_names = san.get_values_for_type(x509.DNSName)
        if dns_names:
            hostname = dns_names[0]
    except x509.ExtensionNotFound:
        pass

    return MisfinIdentity(
        mailbox=mailbox, hostname=hostname, blurb=blurb
    )


_ALGO_PREFIXES = ("sha256:", "sha1:", "sha512:", "md5:")


def normalize_fingerprint(fingerprint: str) -> str:
    """Convert tlacacoca's 'sha256:hexdigest' format to Misfin(C) plain
    lowercase hex (no delimiters).

    Strips known algorithm prefix, removes non-hex chars, lowercases.
    """
    lower = fingerprint.lower()
    for prefix in _ALGO_PREFIXES:
        if lower.startswith(prefix):
            fingerprint = fingerprint[len(prefix):]
            break
    # Remove non-hex characters and lowercase
    return re.sub(r"[^0-9a-fA-F]", "", fingerprint).lower()
