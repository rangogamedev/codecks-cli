# Migrating to 0.6.0 (Codecks v2.96 official API)

codecks-cli 0.6.0 moves to the official Codecks API that shipped in
[Codecks v2.96 "The Magic Key: API & 2FA"](https://www.codecks.io/changelog/release/2.96-the-magic-key-api-2fa/)
(2026-09-24). This guide covers what breaks, how to update, and how to run API tokens safely.

## Why this changed

Before v2.96 Codecks had no official API tokens, so codecks-cli used a copy of your browser login
(the `at` cookie, sent in the `X-Auth-Token` header). That login expired whenever your browser
session ended. Card creation therefore went through a second credential, the
[User Reports](https://manual.codecks.io/user-reports/) report token, which did not expire.

v2.96 added official, long-lived API tokens and deprecated the browser-login header:

- The `X-Auth-Token` header is deprecated and officially stops working on **2026-12-31**.
- In practice it already fails. Since v2.96, requests sent with it have come back as if
  unauthenticated: the account name resolves, but decks and cards are empty
  ([reported in #60](https://github.com/rangogamedev/codecks-cli/pull/60), and reproduced with an
  API token). On 0.5.x the CLI shows that as a misleading `[TOKEN_EXPIRED]`.
- An API token can read, write and create cards, and it lasts until it's revoked or reaches an
  optional expiry date. One token now replaces three.

## Breaking changes

| Area | 0.5.x | 0.6.0 |
|---|---|---|
| `CODECKS_TOKEN` value | browser `at` cookie (DevTools) | API token `cdxut_…` or `cdxat_…` |
| Auth header | `X-Auth-Token` | `Authorization: Bearer <token>` |
| Card creation | User Reports endpoint + `CODECKS_REPORT_TOKEN` | official `dispatch/cards/create` |
| `CODECKS_REPORT_TOKEN`, `CODECKS_ACCESS_KEY` | required to create cards | **removed** (ignored if still in `.env`) |
| `generate-token` command | creates a report token | **removed** |
| `create` without `--deck` | the deck set in Codecks' User Reports settings | `CODECKS_DEFAULT_DECK`, or an error if unset |
| `create --severity` / MCP `severity` | sets report severity | **error**: Codecks cards have no severity field; use `--priority a\|b\|c` |
| Card author | shown as a user report | shown as you (personal token) |
| Python API | `cards.create_card(title, content, severity, file_names=…)` | `cards.create_card(title, content, deck_id=None, **fields)` |
| Python API | `api.report_request`, `api.generate_report_token`, `attachments.upload_report_files` | removed; attach with `attachments.attach_files_to_card` |

New in 0.6.0:
- The `CODECKS_DEFAULT_DECK` setting.
- The `codecks-cli default-deck [name] [--project P]` command. It stores the deck's ID, so a
  renamed deck keeps working and same-named decks in different projects can't be confused.
- `create --priority`.
- Error messages based on the codes the server returns (see [Troubleshooting](#troubleshooting)).

## How to update

1. **Update codecks-cli**:
   ```bash
   pip install -U "git+https://github.com/rangogamedev/codecks-cli.git"
   # with MCP: pip install -U "codecks-cli[mcp] @ git+https://github.com/rangogamedev/codecks-cli.git"
   ```
2. **Create an API token.** In Codecks, open **Your Profile → API Tokens** and create a token
   with *Read & write* access. Copy it right away; it's shown only once. See
   [Best practices](#best-practices) to decide between a personal and an organization token.
3. **Run `codecks-cli setup`.** Paste the token and pick the deck that new cards should go to.
   Setup checks that the token can actually see your projects before it says the token works.
4. **Clean up `.env`.** Delete the `CODECKS_REPORT_TOKEN` and `CODECKS_ACCESS_KEY` lines.
5. **Update every other place the token lives.** Check each of these:
   - MCP server config: the `env` blocks in `.mcp.json`, Claude Desktop, or Cursor.
   - Docker `env_file` / `environment` settings.
   - CI secrets.
   - Anything else that sets `CODECKS_TOKEN`.
6. **Update scripts:**
   - Drop `--severity` (use `--priority`).
   - Replace `generate-token` calls.
   - Python users: see the `create_card` rows in the table above.
7. **Verify:**
   ```bash
   codecks-cli --version        # 0.6.0
   codecks-cli agent-init --agent
   codecks-cli default-deck     # shows the deck new cards go to
   ```

To change the default deck later, run `codecks-cli default-deck <deck name>` (add
`--project <name>` if two projects have a deck with that name), or re-run `codecks-cli setup`
and choose "Change default deck". Setup lists decks as "Deck (Project)". A deck name written
into `.env` by hand also works; the CLI resolves it on each `create`.

## Best practices

- **Personal vs organization token.**
  - **Personal** (`cdxut_`, Your Profile → API Tokens): acts as you, sees the projects you see,
    and new cards show you as the author. Best for your own CLI and agent use.
  - **Organization** (`cdxat_`, Organization Settings → Integrations → API Tokens, owners and
    admins only): belongs to the organization, keeps working if its creator leaves, and only
    sees the projects you select. Best for shared automation and CI. The CLI finds your own
    user through the API's `loggedInUser` query, which only works for personal tokens. With an
    organization token, set `CODECKS_USER_ID` so hand commands and attachments act for the
    right person.
- **Least privilege.** Use *Read* for read-only dashboards and reporting agents. Use *Read & write*
  only where the CLI changes cards. A read-only token that tries to write gets a 403; the
  server's message, which the CLI shows, names the missing permission.
- **Use expiry dates.** Tokens can be created with an optional expiry date. Use one for temporary
  machines, contractors and CI. When a token expires, the CLI says so explicitly.
- **Separate tokens.** Create one token per machine or agent, so you can revoke one without breaking the others.
- **Keep tokens out of chat and git.**
  - Enter tokens through `codecks-cli setup` in a terminal, never by pasting them into an AI
    chat.
  - `.env` is gitignored and written owner-only (0600).
  - If a token leaks, revoke it in Codecks and create a new one.
- **Set `CODECKS_ACCOUNT`.** The CLI sends it as `X-Account`, so a token from another organization
  fails loudly (`token_account_mismatch`) instead of quietly reading the wrong data.
- **Respect the rate limit.** It is 40 requests per 5 seconds per IP. Prefer batch commands and MCP
  batch tools for bulk changes; the CLI already retries using the `retry-after` header.
- **Turning on 2FA** (also new in v2.96) logs out your other browser sessions but doesn't affect
  API tokens.

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `[TOKEN_EXPIRED] Codecks does not recognise the API token…` | typo, revoked, or cut-off token (`invalid_token`) | copy the whole token again, or create a new one |
| `[TOKEN_EXPIRED] The API token has passed its expiry date.` | `token_expired` | create a new token |
| `[TOKEN_EXPIRED] …has been disabled in the organization.` | the personal token's owner was disabled (`not_a_member`) | use a token of an active member, or an organization token |
| `[TOKEN_EXPIRED] An admin has turned off personal API tokens…` | `user_api_tokens_disabled` | ask an admin, or use an organization token |
| `[TOKEN_EXPIRED] Codecks did not accept your API token` during setup/startup | the account did not resolve for this token | check `CODECKS_ACCOUNT` and the token; an old browser-cookie value is not an API token |
| setup says "this token can't see any projects yet" | a new organization with no projects, or an organization token with no projects selected | the token works; create a project or add projects to the token |
| `[SETUP_NEEDED] CODECKS_ACCOUNT does not match…` | `token_account_mismatch` | fix `CODECKS_ACCOUNT`, or use a token from that organization |
| `[ERROR] Codecks denied this request (HTTP 403)…` | read-only token trying to write, or a project not selected for an organization token; the server's message (and, for reads, `requiredScope`) names the missing permission | use a Read & write token, or add the project to the token |
| `[ERROR] No default deck set…` | no `--deck` and no `CODECKS_DEFAULT_DECK` | `codecks-cli default-deck <deck name>` |
| `[ERROR] --severity is no longer supported…` | severity was a User Reports field | use `--priority a\|b\|c` |

## Official documentation

- [Codecks v2.96 release notes: The Magic Key, API & 2FA](https://www.codecks.io/changelog/release/2.96-the-magic-key-api-2fa/)
- [Quick Guide to the Codecks API](https://manual.codecks.io/api/): tokens, permissions, card creation, file uploads, error codes, rate limits
- [Codecks API Reference](https://manual.codecks.io/api-reference/): the query language for reads
- [User Reports & Unity Integration](https://manual.codecks.io/user-reports/): the report-token feature codecks-cli no longer uses
