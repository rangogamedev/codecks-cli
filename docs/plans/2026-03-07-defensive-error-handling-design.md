# Defensive Error Handling & Content Safety Design

**Date:** 2026-03-07
**Status:** Approved
**Scope:** Full defensive refactor — content model, error contracts, cache transparency, test coverage

## Problem

Agent workflows read a card (getting `content` = `"Title\nBody"`), edit the body, and send back `content="Title\nNew body"`. The `update_cards()` code always prepends the old title, producing `"Title\nTitle\nNew body"` — a duplicated title. A point fix was applied (startswith guard), but the root cause is that title/content assembly logic is scattered across `client.py` and `_tools_write.py` with no single source of truth.

Beyond title duplication, analysis identified 5 additional hazard categories:
1. **Whitespace sensitivity** — trailing spaces, `\r\n`, tab characters break title extraction
2. **Opaque errors** — agents can't distinguish retryable (network) from permanent (bad input) failures
3. **Silent stale data** — cache-served responses give no hint they may be outdated
4. **No body-only edit path** — agents must reconstruct full content to change just the body
5. **Cache invalidation gaps** — no test verifies that new mutations get added to the invalidation map

## Design Principles

Inspired by how established tools handle similar problems:
- **Git**: commit message = first line (subject) + blank line + body. Deterministic parsing.
- **Notion/Linear/Jira**: separate title/description fields at API level.
- **CDNs**: `Age` header and `stale-while-revalidate` for cache transparency.

## Part 1: Content Helper Module — `codecks_cli/_content.py`

Single source of truth for Codecks content format: `"Title\n[optional blank line]\nBody"`.

### Functions

```python
def parse_content(content: str | None) -> tuple[str, str]:
    """Split content into (title, body). Title = first non-empty line.
    Returns ("", "") for None/empty. Strips \\r from line endings."""


def serialize_content(title: str, body: str) -> str:
    """Combine title + body into Codecks content format.
    Uses single \\n separator (no blank line) matching Codecks convention."""


def replace_body(content: str | None, new_body: str) -> str:
    """Keep existing title, replace body."""


def replace_title(content: str | None, new_title: str) -> str:
    """Keep existing body, replace title."""


def has_title(content: str | None) -> bool:
    """True if content has a non-empty first line."""
```

### Rules
- `parse_content` strips `\r` before splitting (Windows line ending safety)
- Empty/None content returns `("", "")`
- Title is always the first non-empty line; body is everything after the first `\n`
- `serialize_content` uses `title + "\n" + body` (single newline, no blank line)

### Integration
- `client.py:update_cards()` replaces hand-rolled title extraction with `parse_content()` / `serialize_content()`
- `_tools_write.py:update_cards` treats `content` param as full card content (title + body) — no auto-prepend
- CLI `--content` flag keeps backward-compat body-only behavior via `replace_body()`

## Part 2: MCP Tool Changes

### `update_cards` (modified)
- `content` parameter now means **full card content** (title + body)
- No auto-prepend of old title — what you send is what gets stored
- Docstring updated to make this explicit

### `update_card_body` (new tool)
- Parameters: `card_id: str`, `body: str`
- Reads existing card, uses `replace_body(old_content, body)`, writes back
- Single-card only (no batch) — simpler contract, fewer edge cases
- Use case: agent wants to update description without touching title

### CLI backward compatibility
- `py codecks_api.py update <ids> --content "new body"` continues to work as body-only update
- Internally calls `replace_body()` to preserve title
- No breaking change for CLI users

## Part 3: Error Contract Enhancement

### New fields in `_contract_error()` response

```python
{
    "ok": False,
    "error": "Card not found",
    "error_code": "CARD_NOT_FOUND",  # machine-readable
    "retryable": False,  # agent decision hint
    "schema_version": "1.0",
}
```

### Error classification

| Category | `retryable` | Example `error_code` values |
|----------|-------------|----------------------------|
| Network / timeout | `True` | `NETWORK_ERROR`, `TIMEOUT` |
| Rate limit | `True` | `RATE_LIMITED` |
| Auth expired | `False` | `AUTH_EXPIRED` |
| Bad input | `False` | `INVALID_INPUT`, `CARD_NOT_FOUND` |
| Server error (5xx) | `True` | `SERVER_ERROR` |
| Validation | `False` | `VALIDATION_ERROR`, `INJECTION_DETECTED` |

### Implementation
- `_contract_error()` gains `retryable: bool = False` and `error_code: str = "UNKNOWN"` params
- Each `except` block in `_call()` and tool functions classifies the error
- Backward compatible — new fields are additive

## Part 4: Cache Transparency

### Stale warning
When a cache-served response has age > 80% of TTL:

```python
{
    "ok": True,
    "data": [...],
    "stale_warning": True,  # only present when stale
    "cache_age_seconds": 270,  # how old the cached data is
    "cache_ttl_seconds": 300,  # configured TTL
}
```

### Implementation
- `_core.py` adds `_cache_metadata()` helper that returns age/TTL info
- Cache-aware tools in `_tools_read.py` include stale fields when threshold exceeded
- `stale_warning` key is only present when `True` (no noise on fresh data)
- Agents can choose to call `warm_cache(force=True)` when they see the warning

## Part 5: Test Coverage

### Content helper tests (~10 tests)
- `parse_content`: None, empty, title-only, title+body, title+blank+body, Windows line endings, whitespace-only title
- `serialize_content`: round-trip with `parse_content`
- `replace_body`: preserves title, handles empty original
- `replace_title`: preserves body, handles empty original

### Integration tests (~5 tests)
- `update_cards` with full content (no duplication)
- `update_card_body` MCP tool end-to-end
- `retryable` classification for network vs bad-input errors
- `stale_warning` presence when cache age > 80% TTL
- Cache invalidation map audit: assert every mutation method in `_tools_write.py` and `_tools_comments.py` has a corresponding entry in `_CACHE_INVALIDATION_MAP`

## Migration Plan

1. **Phase 1** (non-breaking): Add `_content.py`, add `update_card_body` tool, enhance error contract
2. **Phase 2** (non-breaking): Wire `client.py` to use content helpers, add cache transparency
3. **Phase 3** (potentially breaking for agents): Change `update_cards` content semantics from body-only to full-content
   - Announce in tool docstring
   - Old agents sending body-only content will get body without title prepended — this is actually safer than the current auto-prepend behavior
   - CLI `--content` flag uses `replace_body()` to maintain backward compat

## Verification

- `py -m pytest tests/ -x --tb=short` — all tests pass
- `py scripts/quality_gate.py` — ruff, mypy, pytest green
- Manual test: read card → update with same content → verify no duplication
