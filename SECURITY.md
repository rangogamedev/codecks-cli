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
- **Never commit `.pm_store.db*` files.** These contain cached card data and are excluded by `.gitignore`.
- **Never commit PM state files** (`.pm_claims.json`, `.pm_last_result.json`, `.pm_undo.json`). These contain session state and are excluded by `.gitignore`.
- **Rotate tokens regularly.** Session tokens expire naturally. Report tokens can be rotated with `py codecks_api.py generate-token`.
- **If a token is exposed:** Rotate it immediately. Session tokens expire with your browser session. Report tokens can be regenerated. Access keys should be rotated from Codecks settings.
- **Report token in URL params** is the official Codecks API design. Treat report tokens as rotatable credentials.

## Attachment path policy

`attach`, `create --file`, and the `attach_files` MCP tool upload local files, so they are the natural target for a prompt-injected agent trying to exfiltrate a credential. Every path is resolved (symlinks followed) before anything is read, and must land inside an **allowed root**:

- the project root,
- the current working directory (for a pip install the project root is `site-packages`, so the directory the user actually works in has to count as well), plus
- any directory listed in the `CODECKS_ATTACH_ALLOW_DIRS` environment variable (`os.pathsep`-separated: `:` on Unix, `;` on Windows). Set it only to directories that genuinely hold shareable assets. An entry that is not an absolute path, is not an existing directory, or names a whole filesystem root is ignored with a warning rather than silently allowing everything.

**Scope of this control.** It constrains an agent that can only call the CLI and the MCP tools: it cannot read a path outside the allowed roots, and it cannot rename or symlink its way to one, because resolution happens before every check. It is *not* a defence against an agent that can also write files — anything such an agent can copy into an allowed root under a non-denylisted name becomes attachable. Where that matters, restrict the agent's write access, not just its attachment paths.

Independent of the root, these are always refused: any path component under the root starting with `.` (`.ssh/`, `.aws/`, `.env*`, `.gdd_tokens.json`), basenames matching `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*token*`, `*secret*`, anything under `/etc`, `/proc`, or `/sys`, and file names containing `"`, CR, or LF (which would let a crafted name inject fields into the upload's `Content-Disposition` header). Backslashes and quotes are escaped when that header is built.

Use `--dry-run` (CLI) or `dry_run=True` (MCP / `CodecksClient.attach_files`) to see exactly which files would be sent — resolved path, size, SHA-256 — without uploading anything.

## Local file permissions

Files holding credentials or private card data are created owner-only (0600) via `mkstemp` + `os.replace`, so they are never briefly world-readable under a permissive umask: `.env`, `.gdd_tokens.json`, `.gdd_cache.md`, and `.pm_store.db` together with its SQLite `-wal` / `-shm` sidecars. These are POSIX permissions; on Windows the chmod is a no-op.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.5.x   | Yes       |
| 0.4.x   | No        |

## Dependency security

- **Dependabot** opens weekly PRs for pip dependencies, GitHub Actions, and the Docker base image.
- **pip-audit** runs in CI on every push/PR, scanning installed dependencies against the PyPI/OSV advisory databases. Run it locally with `pip-audit` or `py scripts/quality_gate.py --audit`. An advisory with no available fix can be temporarily acknowledged with `pip-audit --ignore-vuln <ID>`.
- All GitHub Actions are pinned to commit SHAs and the Docker base image to a digest (supply-chain hardening).

## Scope

This security policy covers the codecks-cli script itself. It does not cover:
- The Codecks API or platform
- Your Codecks account security
- Third-party integrations
