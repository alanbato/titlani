"""Tests for status codes."""


from titlani.protocol.status import (
    StatusCode,
    interpret_status,
    is_auth_failure,
    is_error,
    is_redirect,
    is_success,
)


class TestStatusCode:
    def test_success_code(self):
        assert StatusCode.SUCCESS == 20

    def test_redirect_codes(self):
        assert StatusCode.REDIRECT_TEMPORARY == 30
        assert StatusCode.REDIRECT_PERMANENT == 31

    def test_temporary_failure_codes(self):
        assert StatusCode.TEMPORARY_FAILURE == 40
        assert StatusCode.SERVER_UNAVAILABLE == 41
        assert StatusCode.CGI_ERROR == 42
        assert StatusCode.PROXY_ERROR == 43
        assert StatusCode.SLOW_DOWN == 44
        assert StatusCode.MAILBOX_FULL == 45

    def test_permanent_failure_codes(self):
        assert StatusCode.PERMANENT_FAILURE == 50
        assert StatusCode.MAILBOX_NOT_FOUND == 51
        assert StatusCode.MAILBOX_GONE == 52
        assert StatusCode.DOMAIN_NOT_SERVICED == 53
        assert StatusCode.BAD_REQUEST == 59

    def test_auth_failure_codes(self):
        assert StatusCode.CERTIFICATE_REQUIRED == 60
        assert StatusCode.UNAUTHORIZED_SENDER == 61
        assert StatusCode.CERTIFICATE_INVALID == 62
        assert StatusCode.CERTIFICATE_CHANGED == 63
        assert StatusCode.PROVE_IT == 64


class TestInterpretStatus:
    def test_known_status(self):
        assert interpret_status(20) == "Message delivered"
        assert interpret_status(51) == "Mailbox not found"
        assert interpret_status(60) == "Certificate required"

    def test_unknown_status_in_category(self):
        assert interpret_status(21) == "Success"
        assert interpret_status(35) == "Redirect"
        assert interpret_status(46) == "Temporary failure"

    def test_unknown_category(self):
        assert interpret_status(99) == "Unknown"


class TestStatusHelpers:
    def test_is_success(self):
        assert is_success(20) is True
        assert is_success(29) is True
        assert is_success(30) is False

    def test_is_redirect(self):
        assert is_redirect(30) is True
        assert is_redirect(31) is True
        assert is_redirect(20) is False

    def test_is_error(self):
        assert is_error(40) is True
        assert is_error(50) is True
        assert is_error(59) is True
        assert is_error(60) is False

    def test_is_auth_failure(self):
        assert is_auth_failure(60) is True
        assert is_auth_failure(64) is True
        assert is_auth_failure(50) is False
