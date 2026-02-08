# Status Codes

Misfin status codes follow the Gemini status code scheme — a two-digit code where the first digit indicates the category.

## Status Code Table

| Code | Name | Category | Meta Field Contains |
|------|------|----------|-------------------|
| **20** | SUCCESS | Success | Recipient certificate fingerprint |
| **30** | REDIRECT_TEMPORARY | Redirect | Temporary redirect address |
| **31** | REDIRECT_PERMANENT | Redirect | Permanent redirect address |
| **40** | TEMPORARY_FAILURE | Temporary Failure | Error description |
| **41** | SERVER_UNAVAILABLE | Temporary Failure | Error description |
| **42** | CGI_ERROR | Temporary Failure | Error description |
| **43** | PROXY_ERROR | Temporary Failure | Error description |
| **44** | SLOW_DOWN | Temporary Failure | Retry delay hint |
| **45** | MAILBOX_FULL | Temporary Failure | Error description |
| **50** | PERMANENT_FAILURE | Permanent Failure | Error description |
| **51** | MAILBOX_NOT_FOUND | Permanent Failure | Error description |
| **52** | MAILBOX_GONE | Permanent Failure | Error description |
| **53** | DOMAIN_NOT_SERVICED | Permanent Failure | Error description |
| **59** | BAD_REQUEST | Permanent Failure | Error description |
| **60** | CERTIFICATE_REQUIRED | Auth Failure | Error description |
| **61** | UNAUTHORIZED_SENDER | Auth Failure | Error description |
| **62** | CERTIFICATE_INVALID | Auth Failure | Error description |
| **63** | CERTIFICATE_CHANGED | Auth Failure | Error description |
| **64** | PROVE_IT | Auth Failure | Challenge description |

## Categories

| Range | Category | Description |
|-------|----------|-------------|
| 20-29 | **Success** | Message was delivered |
| 30-39 | **Redirect** | Send to a different address |
| 40-49 | **Temporary Failure** | Try again later |
| 50-59 | **Permanent Failure** | Do not retry |
| 60-69 | **Auth Failure** | Certificate/authentication issue |

## Utility Functions

```python
from titlani.protocol.status import (
    StatusCode,
    interpret_status,
    is_success,
    is_redirect,
    is_error,
    is_auth_failure,
)
```

### `interpret_status(status: int) -> str`

Returns a human-readable description:

```python
interpret_status(20)  # "Message delivered"
interpret_status(51)  # "Mailbox not found"
interpret_status(99)  # "Unknown status"
```

### `is_success(status: int) -> bool`

```python
is_success(20)  # True
is_success(51)  # False
```

### `is_redirect(status: int) -> bool`

```python
is_redirect(30)  # True
is_redirect(31)  # True
is_redirect(20)  # False
```

### `is_error(status: int) -> bool`

Returns `True` for both temporary (40-49) and permanent (50-59) failures:

```python
is_error(40)  # True
is_error(51)  # True
is_error(60)  # False  (auth failure, not general error)
```

### `is_auth_failure(status: int) -> bool`

```python
is_auth_failure(60)  # True
is_auth_failure(64)  # True
is_auth_failure(50)  # False
```

## Using StatusCode Enum

```python
from titlani import StatusCode, MisfinResponse

response = MisfinResponse(status=StatusCode.SUCCESS, meta="fingerprint_here")
response = MisfinResponse(status=StatusCode.MAILBOX_NOT_FOUND, meta="No such mailbox")
```

The `StatusCode` enum is an `IntEnum`, so it can be used anywhere an integer status code is expected.
