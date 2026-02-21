"""Tests for exception hierarchy and backward-compat re-exports."""

from codecks_cli.exceptions import CliError, HTTPError, SetupError


class TestExceptionHierarchy:
    def test_cli_error_is_exception(self):
        assert issubclass(CliError, Exception)

    def test_setup_error_is_cli_error(self):
        assert issubclass(SetupError, CliError)

    def test_http_error_is_exception(self):
        assert issubclass(HTTPError, Exception)

    def test_http_error_not_cli_error(self):
        assert not issubclass(HTTPError, CliError)

    def test_cli_error_exit_code(self):
        assert CliError.exit_code == 1

    def test_setup_error_exit_code(self):
        assert SetupError.exit_code == 2


class TestBackwardCompat:
    def test_config_re_exports_cli_error(self):
        from codecks_cli.config import CliError as ConfigCliError

        assert ConfigCliError is CliError

    def test_config_re_exports_setup_error(self):
        from codecks_cli.config import SetupError as ConfigSetupError

        assert ConfigSetupError is SetupError

    def test_api_re_exports_http_error(self):
        from codecks_cli.api import HTTPError as ApiHTTPError

        assert ApiHTTPError is HTTPError

    def test_init_re_exports(self):
        from codecks_cli import CliError as InitCliError
        from codecks_cli import SetupError as InitSetupError

        assert InitCliError is CliError
        assert InitSetupError is SetupError


class TestHTTPErrorAttrs:
    def test_http_error_attrs(self):
        err = HTTPError(404, "Not Found", "body text", {"X-Req": "abc"})
        assert err.code == 404
        assert err.reason == "Not Found"
        assert err.body == "body text"
        assert err.headers == {"X-Req": "abc"}

    def test_http_error_default_headers(self):
        err = HTTPError(500, "Server Error", "")
        assert err.headers == {}
