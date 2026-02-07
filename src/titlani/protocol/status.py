"""Misfin status codes compatible with Gemini status code categories."""

from enum import IntEnum


class StatusCode(IntEnum):
    SUCCESS = 20
    REDIRECT_TEMPORARY = 30
    REDIRECT_PERMANENT = 31
    TEMPORARY_FAILURE = 40
    SERVER_UNAVAILABLE = 41
    CGI_ERROR = 42
    PROXY_ERROR = 43
    SLOW_DOWN = 44
    MAILBOX_FULL = 45
    PERMANENT_FAILURE = 50
    MAILBOX_NOT_FOUND = 51
    MAILBOX_GONE = 52
    DOMAIN_NOT_SERVICED = 53
    BAD_REQUEST = 59
    CERTIFICATE_REQUIRED = 60
    UNAUTHORIZED_SENDER = 61
    CERTIFICATE_INVALID = 62
    CERTIFICATE_CHANGED = 63
    PROVE_IT = 64


_STATUS_DESCRIPTIONS: dict[int, str] = {
    20: "Message delivered",
    30: "Send here instead",
    31: "Send here forever",
    40: "Temporary error",
    41: "Server unavailable",
    42: "CGI error",
    43: "Proxying error",
    44: "Slow down",
    45: "Mailbox full",
    50: "Permanent error",
    51: "Mailbox not found",
    52: "Mailbox gone",
    53: "Domain not serviced",
    59: "Bad request",
    60: "Certificate required",
    61: "Unauthorized sender",
    62: "Certificate invalid",
    63: "Certificate changed",
    64: "Prove it",
}


def interpret_status(status: int) -> str:
    if status in _STATUS_DESCRIPTIONS:
        return _STATUS_DESCRIPTIONS[status]
    category = status // 10
    category_names = {
        2: "Success",
        3: "Redirect",
        4: "Temporary failure",
        5: "Permanent failure",
        6: "Authentication failure",
    }
    return category_names.get(category, "Unknown")


def is_success(status: int) -> bool:
    return 20 <= status < 30


def is_redirect(status: int) -> bool:
    return 30 <= status < 40


def is_error(status: int) -> bool:
    return 40 <= status < 60


def is_auth_failure(status: int) -> bool:
    return 60 <= status < 70
