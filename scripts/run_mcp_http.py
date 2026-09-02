"""Run the Codecks MCP server in streamable-http mode.

Environment variables:
    ``MCP_HTTP_HOST``             Bind address. Defaults to ``127.0.0.1`` — the
                                  server is unauthenticated, so it must not be
                                  exposed on a public interface. Inside Docker
                                  set it to ``0.0.0.0`` and publish the port on
                                  loopback only (see ``docker-compose.yml``).
    ``MCP_HTTP_PORT``             TCP port. Defaults to ``8808``.
    ``MCP_HTTP_ALLOWED_HOSTS``    Comma-separated ``Host`` header allowlist used
                                  when the bind address is not loopback.
                                  Defaults to
                                  ``localhost:*,127.0.0.1:*,[::1]:*``.
    ``MCP_HTTP_ALLOWED_ORIGINS``  Comma-separated ``Origin`` header allowlist,
                                  same conditions. Defaults to ``http://localhost:*,
                                  http://127.0.0.1:*,http://[::1]:*``.

The MCP SDK only auto-enables DNS-rebinding protection when the bind address is
a loopback address; for any other address this module builds the
``TransportSecuritySettings`` explicitly so Host/Origin validation stays on.
"""

import os

from mcp.server.transport_security import TransportSecuritySettings

from codecks_cli.mcp_server import mcp

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "8808"

#: Bind addresses for which the SDK already turns on DNS-rebinding protection.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Mirrors the SDK's own loopback allowlists, IPv6 loopback included.
DEFAULT_ALLOWED_HOSTS = "localhost:*,127.0.0.1:*,[::1]:*"
DEFAULT_ALLOWED_ORIGINS = "http://localhost:*,http://127.0.0.1:*,http://[::1]:*"


def _csv_env(name: str, default: str) -> list[str]:
    """Parse a comma-separated env var into a list, falling back to *default*."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        raw = default
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_transport_security(host: str) -> TransportSecuritySettings | None:
    """Return transport security settings for a bind address, or ``None``.

    ``None`` means "let the SDK decide": for loopback addresses it already
    enables DNS-rebinding protection with loopback Host/Origin allowlists. For
    any non-loopback bind address the SDK would leave the protection off, so we
    build the settings explicitly from ``MCP_HTTP_ALLOWED_HOSTS`` /
    ``MCP_HTTP_ALLOWED_ORIGINS``.
    """
    if host in LOOPBACK_HOSTS:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_csv_env("MCP_HTTP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
        allowed_origins=_csv_env("MCP_HTTP_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS),
    )


def main() -> None:
    """Start the streamable-http MCP server."""
    host = os.environ.get("MCP_HTTP_HOST", DEFAULT_HOST)
    mcp.run(
        transport="streamable-http",
        host=host,
        port=int(os.environ.get("MCP_HTTP_PORT", DEFAULT_PORT)),
        transport_security=build_transport_security(host),
    )


if __name__ == "__main__":
    main()
