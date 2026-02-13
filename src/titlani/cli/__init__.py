"""Rich CLI display components for Titlani."""

from .display import (
    confirm_action,
    display_gemmail_list,
    display_gemmail_message,
    display_identity_info,
    display_server_config,
    display_spki_list,
    display_tofu_list,
    display_verification_list,
    display_version_info,
    format_fingerprint,
    format_relative_time,
    format_status_response,
)

__all__ = [
    "confirm_action",
    "display_gemmail_list",
    "display_gemmail_message",
    "display_identity_info",
    "display_server_config",
    "display_spki_list",
    "display_tofu_list",
    "display_verification_list",
    "display_version_info",
    "format_fingerprint",
    "format_relative_time",
    "format_status_response",
]
