# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in codecks-cli, **please do not open a public issue.** Instead, report it privately:

- Use [GitHub Security Advisories](../../security/advisories/new) to report directly on this repo
- Or email the maintainer (see GitHub profile)

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide updates as the issue is resolved.

## Token safety

This tool handles Codecks API tokens. Please follow these practices:

- **Never commit `.env` files.** The `.gitignore` already protects this, but double-check before pushing.
- **Rotate tokens regularly.** Session tokens expire naturally. Report tokens can be rotated with `py codecks_api.py generate-token`.
- **If a token is exposed:** Rotate it immediately. Session tokens expire with your browser session. Report tokens can be regenerated. Access keys should be rotated from Codecks settings.
- **Report token in URL params** is the official Codecks API design. Treat report tokens as rotatable credentials.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.4.x   | Yes       |

## Scope

This security policy covers the codecks-cli script itself. It does not cover:
- The Codecks API or platform
- Your Codecks account security
- Third-party integrations
