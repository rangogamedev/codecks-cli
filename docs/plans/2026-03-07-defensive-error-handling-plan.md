# Defensive Error Handling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate content corruption bugs, add agent-friendly error classification, and surface cache staleness — making the agent workflow deterministic and self-healing.

**Architecture:** New `_content.py` module as single source of truth for title/body parsing. Enhanced `_contract_error()` with `retryable`/`error_code` fields. Cache-served responses include `stale_warning` when age exceeds 80% TTL. New `update_card_body` MCP tool for body-only edits.

**Tech Stack:** Python 3.10+ stdlib only (no new deps). pytest for tests. ruff + mypy for quality.

---

### Task 1: Content Helper Module — Tests

**Files:**
- Create: `tests/test_content.py`

**Step 1: Write the full test file for `_content.py`**

```python
"""Tests for content parsing helpers (codecks_cli/_content.py)."""

from codecks_cli._content import (
    has_title,
    parse_content,
    replace_body,
    replace_title,
    serialize_content,
)


class TestParseContent:
    def test_none_returns_empty(self):
        assert parse_content(None) == ("", "")

    def test_empty_string_returns_empty(self):
        assert parse_content("") == ("", "")

    def test_title_only(self):
        assert parse_content("My Title") == ("My Title", "")

    def test_title_and_body(self):
        assert parse_content("My Title\nSome body text") == ("My Title", "Some body text")

    def test_title_blank_line_body(self):
        assert parse_content("My Title\n\nSome body text") == ("My Title", "\nSome body text")

    def test_windows_line_endings(self):
        assert parse_content("My Title\r\nBody text\r\nMore") == ("My Title", "Body text\nMore")

    def test_whitespace_only_title(self):
        assert parse_content("   \nBody text") == ("   ", "Body text")

    def test_multiline_body(self):
        title, body = parse_content("Title\nLine 1\nLine 2\nLine 3")
        assert title == "Title"
        assert body == "Line 1\nLine 2\nLine 3"

    def test_trailing_newline(self):
        title, body = parse_content("Title\nBody\n")
        assert title == "Title"
        assert body == "Body\n"


class TestSerializeContent:
    def test_title_and_body(self):
        assert serialize_content("Title", "Body") == "Title\nBody"

    def test_empty_body(self):
        assert serialize_content("Title", "") == "Title"

    def test_empty_title(self):
        assert serialize_content("", "Body") == "\nBody"

    def test_both_empty(self):
        assert serialize_content("", "") == ""

    def test_roundtrip(self):
        original = "My Title\nBody content here"
        title, body = parse_content(original)
        assert serialize_content(title, body) == original


class TestReplaceBody:
    def test_basic(self):
        assert replace_body("Old Title\nOld body", "New body") == "Old Title\nNew body"

    def test_empty_original(self):
        assert replace_body(None, "New body") == "\nNew body"

    def test_empty_string_original(self):
        assert replace_body("", "New body") == "\nNew body"

    def test_preserves_title(self):
        result = replace_body("Keep This Title\nOld stuff", "Brand new content")
        assert result.startswith("Keep This Title\n")
        assert "Old stuff" not in result

    def test_title_only_original(self):
        assert replace_body("Just Title", "New body") == "Just Title\nNew body"


class TestReplaceTitle:
    def test_basic(self):
        assert replace_title("Old Title\nKeep body", "New Title") == "New Title\nKeep body"

    def test_empty_original(self):
        assert replace_title(None, "New Title") == "New Title"

    def test_empty_string_original(self):
        assert replace_title("", "New Title") == "New Title"

    def test_preserves_body(self):
        result = replace_title("Old Title\nBody line 1\nBody line 2", "New Title")
        assert result == "New Title\nBody line 1\nBody line 2"

    def test_title_only_original(self):
        assert replace_title("Old Title", "New Title") == "New Title"


class TestHasTitle:
    def test_none(self):
        assert has_title(None) is False

    def test_empty(self):
        assert has_title("") is False

    def test_has_title(self):
        assert has_title("My Title\nBody") is True

    def test_title_only(self):
        assert has_title("My Title") is True

    def test_newline_only(self):
        assert has_title("\nBody") is False
```

**Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_content.py -x --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'codecks_cli._content'`

**Step 3: Commit test file**

```bash
git add tests/test_content.py
git commit -m "Add tests for content parsing helpers"
```

---

### Task 2: Content Helper Module — Implementation

**Files:**
- Create: `codecks_cli/_content.py`

**Step 1: Write the implementation**

```python
"""Content parsing helpers for Codecks card format.

Codecks stores card title as the first line of the ``content`` field:
``"My Title\\nBody text here"``. This module provides deterministic
parsing and serialization so title/body logic has a single source of truth.
"""

from __future__ import annotations


def parse_content(content: str | None) -> tuple[str, str]:
    """Split content into (title, body).

    Title is the first line. Body is everything after the first ``\\n``.
    Returns ``("", "")`` for ``None`` or empty string.
    Strips ``\\r`` from line endings for Windows safety.
    """
    if not content:
        return ("", "")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    parts = content.split("\n", 1)
    title = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    return (title, body)


def serialize_content(title: str, body: str) -> str:
    """Combine title and body into Codecks content format.

    Uses single ``\\n`` separator. Returns empty string if both are empty.
    Returns title alone (no trailing newline) if body is empty.
    """
    if not title and not body:
        return ""
    if not body:
        return title
    return title + "\n" + body


def replace_body(content: str | None, new_body: str) -> str:
    """Keep existing title, replace body."""
    title, _ = parse_content(content)
    return serialize_content(title, new_body)


def replace_title(content: str | None, new_title: str) -> str:
    """Keep existing body, replace title."""
    _, body = parse_content(content)
    return serialize_content(new_title, body)


def has_title(content: str | None) -> bool:
    """Return True if content has a non-empty first line."""
    if not content:
        return False
    first_line = content.split("\n", 1)[0]
    return len(first_line.strip()) > 0
```

**Step 2: Run tests to verify they pass**

Run: `py -m pytest tests/test_content.py -x --tb=short`
Expected: All 23 tests PASS

**Step 3: Run ruff + mypy on the new module**

Run: `py -m ruff check codecks_cli/_content.py && py -m ruff format --check codecks_cli/_content.py`
Expected: Clean

**Step 4: Add to mypy targets**

Modify: `scripts/quality_gate.py` — add `"codecks_cli/_content.py"` to the `MYPY_TARGETS` list.

**Step 5: Run mypy on the new module**

Run: `py scripts/quality_gate.py --mypy-only`
Expected: Clean

**Step 6: Commit**

```bash
git add codecks_cli/_content.py scripts/quality_gate.py
git commit -m "Add content parsing helper module"
```

---

### Task 3: Wire `client.py` to Use Content Helpers

**Files:**
- Modify: `codecks_cli/client.py:908-945`
- Test: `tests/test_client.py` (existing tests cover this path)

**Step 1: Write new tests for edge cases in `test_client.py`**

Add to `TestUpdateCards` class (after existing title/content tests near line 563):

```python
    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.get_card")
    def test_content_with_windows_line_endings(self, mock_get, mock_update):
        """Windows line endings should not break title detection."""
        mock_get.return_value = {"card": {"c1": {"content": "Title\r\nOld body"}}}
        mock_update.return_value = {}
        client = _client()
        client.update_cards(["c1"], content="New body")
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["content"] == "Title\nNew body"

    @patch("codecks_cli.client.update_card")
    @patch("codecks_cli.client.get_card")
    def test_content_empty_old_content(self, mock_get, mock_update):
        """When old content is empty, content should pass through as-is."""
        mock_get.return_value = {"card": {"c1": {"content": ""}}}
        mock_update.return_value = {}
        client = _client()
        client.update_cards(["c1"], content="New body")
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["content"] == "\nNew body"
```

**Step 2: Run new tests to see them fail**

Run: `py -m pytest tests/test_client.py::TestUpdateCards::test_content_with_windows_line_endings tests/test_client.py::TestUpdateCards::test_content_empty_old_content -x --tb=short`
Expected: `test_content_with_windows_line_endings` FAILS (old code doesn't strip `\r`)

**Step 3: Refactor `client.py:908-945` to use `_content.py`**

Replace the entire `if title is not None or content is not None:` block at `client.py:908-945` with:

```python
        if title is not None or content is not None:
            from codecks_cli._content import parse_content, replace_body, serialize_content

            if title is not None and len(card_ids) > 1:
                raise CliError("[ERROR] --title can only be used with a single card.")
            if content is not None and len(card_ids) > 1:
                raise CliError("[ERROR] --content can only be used with a single card.")

            if title is not None and content is not None:
                # Both provided: combine new title with new content
                update_kwargs["content"] = serialize_content(title, content)
            elif title is not None:
                # Title only: replace first line, preserve existing body
                card_data = get_card(card_ids[0])
                cards = card_data.get("card", {})
                if not cards:
                    raise CliError(f"[ERROR] Card '{card_ids[0]}' not found.")
                for _k, c in cards.items():
                    old_content = c.get("content") or ""
                    _, old_body = parse_content(old_content)
                    update_kwargs["content"] = serialize_content(title, old_body)
                    break
            else:
                # Content only (CLI backward compat): treat as body, preserve title
                assert content is not None  # mypy: narrowed by elif chain
                card_data = get_card(card_ids[0])
                cards = card_data.get("card", {})
                if not cards:
                    raise CliError(f"[ERROR] Card '{card_ids[0]}' not found.")
                for _k, c in cards.items():
                    old_content = c.get("content") or ""
                    old_title, _ = parse_content(old_content)
                    if content.startswith(old_title + "\n") or content == old_title:
                        # Content already includes the title — use as-is
                        update_kwargs["content"] = content
                    else:
                        # Body-only content — prepend existing title
                        update_kwargs["content"] = serialize_content(old_title, content)
                    break
```

**Step 4: Run full test suite for `test_client.py`**

Run: `py -m pytest tests/test_client.py -x --tb=short`
Expected: All tests PASS (including existing title/content tests + new edge cases)

**Step 5: Commit**

```bash
git add codecks_cli/client.py tests/test_client.py
git commit -m "Refactor client content handling to use _content helpers"
```

---

### Task 4: Error Contract Enhancement

**Files:**
- Modify: `codecks_cli/mcp_server/_core.py:248-259` (`_contract_error`)
- Modify: `codecks_cli/mcp_server/_core.py:380-398` (`_call`)
- Test: `tests/test_mcp_server.py`

**Step 1: Write tests for error classification**

Add to `tests/test_mcp_server.py` near the end:

```python
class TestErrorContract:
    def test_contract_error_has_retryable_and_error_code(self):
        result = _core._contract_error("boom", "error", retryable=True, error_code="NETWORK_ERROR")
        assert result["ok"] is False
        assert result["retryable"] is True
        assert result["error_code"] == "NETWORK_ERROR"
        assert result["error"] == "boom"

    def test_contract_error_defaults(self):
        result = _core._contract_error("bad input")
        assert result["retryable"] is False
        assert result["error_code"] == "UNKNOWN"

    @patch("codecks_cli.mcp_server._core.CodecksClient")
    def test_call_setup_error_not_retryable(self, MockClient):
        from codecks_cli.exceptions import SetupError
        MockClient.return_value.get_account.side_effect = SetupError("no token")
        _core._client = None
        result = _core._call("get_account")
        assert result["ok"] is False
        assert result["retryable"] is False
        assert result["error_code"] == "SETUP_ERROR"

    @patch("codecks_cli.mcp_server._core.CodecksClient")
    def test_call_unexpected_error_retryable(self, MockClient):
        MockClient.return_value.get_account.side_effect = ConnectionError("timeout")
        _core._client = None
        result = _core._call("get_account")
        assert result["ok"] is False
        assert result["retryable"] is True
        assert result["error_code"] == "UNEXPECTED_ERROR"

    @patch("codecks_cli.mcp_server._core.CodecksClient")
    def test_call_cli_error_not_retryable(self, MockClient):
        from codecks_cli.exceptions import CliError
        MockClient.return_value.get_account.side_effect = CliError("bad id")
        _core._client = None
        result = _core._call("get_account")
        assert result["ok"] is False
        assert result["retryable"] is False
        assert result["error_code"] == "CLI_ERROR"
```

**Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_mcp_server.py::TestErrorContract -x --tb=short`
Expected: FAIL — `_contract_error()` doesn't accept `retryable`/`error_code` yet

**Step 3: Update `_contract_error()` in `_core.py:248-259`**

Replace:

```python
def _contract_error(message: str, error_type: str = "error") -> dict:
    """Return a stable MCP error envelope with legacy compatibility fields."""
    return {
        "ok": False,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "type": error_type,  # legacy
        "error": message,  # legacy
        "error_detail": {
            "type": error_type,
            "message": message,
        },
    }
```

With:

```python
def _contract_error(
    message: str,
    error_type: str = "error",
    *,
    retryable: bool = False,
    error_code: str = "UNKNOWN",
) -> dict:
    """Return a stable MCP error envelope with legacy compatibility fields."""
    return {
        "ok": False,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "type": error_type,  # legacy
        "error": message,  # legacy
        "retryable": retryable,
        "error_code": error_code,
        "error_detail": {
            "type": error_type,
            "message": message,
        },
    }
```

**Step 4: Update `_call()` in `_core.py:380-398` with error classification**

Replace:

```python
    except SetupError as e:
        return _contract_error(str(e), "setup")
    except CliError as e:
        return _contract_error(str(e), "error")
    except Exception as e:
        return _contract_error(f"Unexpected error: {e}", "error")
```

With:

```python
    except SetupError as e:
        return _contract_error(str(e), "setup", retryable=False, error_code="SETUP_ERROR")
    except CliError as e:
        return _contract_error(str(e), "error", retryable=False, error_code="CLI_ERROR")
    except (ConnectionError, TimeoutError, OSError) as e:
        return _contract_error(
            f"Network error: {e}", "error", retryable=True, error_code="NETWORK_ERROR"
        )
    except Exception as e:
        return _contract_error(
            f"Unexpected error: {e}", "error", retryable=True, error_code="UNEXPECTED_ERROR"
        )
```

**Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/test_mcp_server.py::TestErrorContract -x --tb=short`
Expected: All 5 tests PASS

**Step 6: Run full MCP test suite to check for regressions**

Run: `py -m pytest tests/test_mcp_server.py -x --tb=short`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add codecks_cli/mcp_server/_core.py tests/test_mcp_server.py
git commit -m "Add retryable and error_code to error contract"
```

---

### Task 5: Cache Transparency — Stale Warning

**Files:**
- Modify: `codecks_cli/mcp_server/_core.py:71-80` (`_get_cache_metadata`)
- Test: `tests/test_mcp_cache.py`

**Step 1: Write test for stale warning**

Add to `tests/test_mcp_cache.py`:

```python
class TestStaleWarning:
    def test_metadata_includes_stale_warning_when_old(self):
        """Cache age > 80% TTL should include stale_warning."""
        import time
        from codecks_cli import config

        _core._snapshot_cache = {"fetched_at": "2026-03-07T00:00:00Z"}
        # Simulate cache loaded 250s ago (>80% of 300s TTL)
        _core._cache_loaded_at = time.monotonic() - 250
        meta = _core._get_cache_metadata()
        assert meta["cached"] is True
        assert meta["stale_warning"] is True
        assert meta["cache_ttl_seconds"] == config.CACHE_TTL_SECONDS

    def test_metadata_no_stale_warning_when_fresh(self):
        """Cache age < 80% TTL should NOT include stale_warning."""
        import time

        _core._snapshot_cache = {"fetched_at": "2026-03-07T00:00:00Z"}
        # Simulate cache loaded 50s ago (<80% of 300s)
        _core._cache_loaded_at = time.monotonic() - 50
        meta = _core._get_cache_metadata()
        assert meta["cached"] is True
        assert "stale_warning" not in meta

    def test_metadata_no_cache(self):
        """No cache should return cached=False."""
        _core._snapshot_cache = None
        meta = _core._get_cache_metadata()
        assert meta["cached"] is False
        assert "stale_warning" not in meta
```

**Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_mcp_cache.py::TestStaleWarning -x --tb=short`
Expected: FAIL — `stale_warning` key not present yet

**Step 3: Update `_get_cache_metadata()` in `_core.py:71-80`**

Replace:

```python
def _get_cache_metadata() -> dict:
    """Return cache staleness info for inclusion in tool responses."""
    if _snapshot_cache is None:
        return {"cached": False}
    age = time.monotonic() - _cache_loaded_at
    return {
        "cached": True,
        "cache_age_seconds": round(age, 1),
        "cache_fetched_at": _snapshot_cache.get("fetched_at", ""),
    }
```

With:

```python
def _get_cache_metadata() -> dict:
    """Return cache staleness info for inclusion in tool responses.

    Includes ``stale_warning: True`` when cache age exceeds 80% of TTL.
    """
    if _snapshot_cache is None:
        return {"cached": False}
    age = time.monotonic() - _cache_loaded_at
    meta: dict = {
        "cached": True,
        "cache_age_seconds": round(age, 1),
        "cache_fetched_at": _snapshot_cache.get("fetched_at", ""),
    }
    if CACHE_TTL_SECONDS > 0 and age > CACHE_TTL_SECONDS * 0.8:
        meta["stale_warning"] = True
        meta["cache_ttl_seconds"] = CACHE_TTL_SECONDS
    return meta
```

**Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_mcp_cache.py::TestStaleWarning -x --tb=short`
Expected: All 3 tests PASS

**Step 5: Run full cache test suite**

Run: `py -m pytest tests/test_mcp_cache.py -x --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add codecks_cli/mcp_server/_core.py tests/test_mcp_cache.py
git commit -m "Add stale_warning to cache metadata when age exceeds 80% TTL"
```

---

### Task 6: New `update_card_body` MCP Tool

**Files:**
- Modify: `codecks_cli/mcp_server/_tools_write.py` (add function + register)
- Modify: `codecks_cli/mcp_server/__init__.py` (add re-export)
- Test: `tests/test_mcp_server.py`

**Step 1: Write test for `update_card_body`**

Add to `tests/test_mcp_server.py`:

```python
class TestUpdateCardBody:
    @patch("codecks_cli.mcp_server._core.CodecksClient")
    def test_update_card_body_replaces_body_preserves_title(self, MockClient):
        client = _mock_client(
            get_card={"id": _C1, "title": "Keep Title", "content": "Keep Title\nOld body"},
            update_cards={"ok": True, "updated": 1, "per_card": [{"card_id": _C1, "ok": True}]},
        )
        MockClient.return_value = client
        result = mcp_mod.update_card_body(card_id=_C1, body="New body text")
        # Verify update_cards was called with the right content
        client.update_cards.assert_called_once()
        call_kwargs = client.update_cards.call_args
        assert "Keep Title" in call_kwargs[1].get("content", "") or call_kwargs[0][1] if call_kwargs[0] else ""

    @patch("codecks_cli.mcp_server._core.CodecksClient")
    def test_update_card_body_invalid_uuid(self, MockClient):
        result = mcp_mod.update_card_body(card_id=_BAD, body="New body")
        assert result["ok"] is False
```

**Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_mcp_server.py::TestUpdateCardBody -x --tb=short`
Expected: FAIL — `update_card_body` not defined

**Step 3: Add `update_card_body` to `_tools_write.py`**

Add before the `register()` function (around line 349):

```python
def update_card_body(card_id: str, body: str) -> dict:
    """Update only the body/description of a card, preserving its title.

    Use this when you want to change the card description without touching
    the title. For full content replacement, use update_cards with content=.

    Args:
        card_id: Full 36-char UUID.
        body: New body text (replaces everything after the title line).

    Returns:
        Dict with ok and update result.
    """
    try:
        _validate_uuid(card_id)
        body = _validate_input(body, "content")
    except CliError as e:
        return _finalize_tool_result(_contract_error(str(e), "error"))

    from codecks_cli._content import replace_body

    # Read existing card to get current content
    card_result = _call("get_card", card_id=card_id)
    if isinstance(card_result, dict) and card_result.get("ok") is False:
        return _finalize_tool_result(card_result)

    old_content = ""
    if isinstance(card_result, dict):
        old_content = card_result.get("content") or ""

    new_content = replace_body(old_content, body)
    return _finalize_tool_result(
        _call("update_cards", card_ids=[card_id], content=new_content)
    )
```

**Step 4: Register the new tool in the `register()` function**

In `_tools_write.py`, add to `register()`:

```python
    mcp.tool()(update_card_body)
```

**Step 5: Add re-export in `__init__.py`**

In `codecks_cli/mcp_server/__init__.py`, add `update_card_body` to the `_tools_write` re-export block:

```python
from codecks_cli.mcp_server._tools_write import (  # noqa: E402, F401
    add_to_hand,
    archive_card,
    create_card,
    delete_card,
    list_hand,
    mark_done,
    mark_started,
    remove_from_hand,
    scaffold_feature,
    split_features,
    unarchive_card,
    update_card_body,
    update_cards,
)
```

**Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/test_mcp_server.py::TestUpdateCardBody -x --tb=short`
Expected: All tests PASS

**Step 7: Run full MCP test suite**

Run: `py -m pytest tests/test_mcp_server.py -x --tb=short`
Expected: All tests PASS

**Step 8: Commit**

```bash
git add codecks_cli/mcp_server/_tools_write.py codecks_cli/mcp_server/__init__.py tests/test_mcp_server.py
git commit -m "Add update_card_body MCP tool for body-only edits"
```

---

### Task 7: Update `update_cards` MCP Docstring

**Files:**
- Modify: `codecks_cli/mcp_server/_tools_write.py:80-101` (docstring)

**Step 1: Update the docstring**

In `_tools_write.py`, change the `update_cards` docstring's `title/content` line (around line 90-91):

From:
```python
        title/content: Single card only. Content that already starts with the
            existing title is sent as-is; otherwise the title is auto-preserved
            as first line. If both title and content are set, they merge.
```

To:
```python
        title/content: Single card only. Content is full card text (title + body).
            If content already starts with the existing title, it is sent as-is;
            otherwise the existing title is preserved as first line (CLI backward
            compat). Use update_card_body() for body-only edits.
            If both title and content are set, they merge.
```

**Step 2: Commit**

```bash
git add codecks_cli/mcp_server/_tools_write.py
git commit -m "Clarify update_cards content semantics in docstring"
```

---

### Task 8: Cache Invalidation Map Audit Test

**Files:**
- Test: `tests/test_mcp_cache.py`

**Step 1: Write audit test**

Add to `tests/test_mcp_cache.py`:

```python
class TestCacheInvalidationMapCompleteness:
    def test_all_mutation_methods_in_invalidation_map(self):
        """Every method in _MUTATION_METHODS must have an entry in _CACHE_INVALIDATION_MAP."""
        missing = _core._MUTATION_METHODS - set(_core._CACHE_INVALIDATION_MAP.keys())
        assert missing == set(), (
            f"Mutation methods missing from _CACHE_INVALIDATION_MAP: {missing}. "
            f"Add entries (even empty lists) for each new mutation method."
        )

    def test_invalidation_map_has_no_stale_entries(self):
        """Every key in _CACHE_INVALIDATION_MAP must be in _MUTATION_METHODS or _ALLOWED_METHODS."""
        known = _core._MUTATION_METHODS | _core._ALLOWED_METHODS
        stale = set(_core._CACHE_INVALIDATION_MAP.keys()) - known
        assert stale == set(), (
            f"_CACHE_INVALIDATION_MAP has entries for unknown methods: {stale}. "
            f"Remove stale entries or add methods to _ALLOWED_METHODS/_MUTATION_METHODS."
        )
```

**Step 2: Run tests to verify they pass**

Run: `py -m pytest tests/test_mcp_cache.py::TestCacheInvalidationMapCompleteness -x --tb=short`
Expected: PASS — current map already covers all mutation methods

**Step 3: Commit**

```bash
git add tests/test_mcp_cache.py
git commit -m "Add cache invalidation map completeness audit test"
```

---

### Task 9: Full Quality Gate

**Files:** (none modified — verification only)

**Step 1: Run full test suite**

Run: `py -m pytest tests/ -x --tb=short`
Expected: All tests PASS (820+ tests)

**Step 2: Run quality gate**

Run: `py scripts/quality_gate.py`
Expected: ruff check clean, ruff format clean, mypy clean, pytest clean

**Step 3: No commit needed — verification only**

---

### Task 10: Update Documentation

**Files:**
- Modify: `AGENTS.md` — add `_content.py` to architecture, update tool count (51), add Known Bug #11
- Modify: `CLAUDE.md` — update tool count (51)
- Modify: `PROJECT_INDEX.md` — add `_content.py` module
- Modify: `.claude/maps/mcp-server.md` — add `update_card_body` to tool index

**Step 1: Update AGENTS.md**

- Architecture section: add `_content.py — Content parsing helpers (parse/serialize title+body)` to the module list
- Tool count: 42 core → 43 core (add `update_card_body`), 50 → 51 total
- Known Bugs Fixed: add #11: "`_contract_error` responses now include `retryable` and `error_code` for agent error recovery. Cache-served responses include `stale_warning` when age exceeds 80% TTL."

**Step 2: Update CLAUDE.md**

- MCP Server section: update tool count from 50 to 51
- Add note: "`update_card_body` — body-only edit tool, preserves title automatically"

**Step 3: Update PROJECT_INDEX.md**

- Add `_content.py` to the module list with description "Content title/body parse, serialize, replace"

**Step 4: Update `.claude/maps/mcp-server.md`**

- Update tool count: 50 → 51
- Add `update_card_body` to Card Operations table (8 total now)
- Note the new error contract fields in a brief section

**Step 5: Commit**

```bash
git add AGENTS.md CLAUDE.md PROJECT_INDEX.md .claude/maps/mcp-server.md
git commit -m "Update docs for content helpers, error contract, and new tool"
```

---

### Task 11: Update Project Memory

**Files:**
- Modify: `C:\Users\USER\.claude\projects\C--Users-USER-GitHubDirectory-codecks-cli\memory\MEMORY.md`

**Step 1: Update memory**

Add to the Architecture section:
- `_content.py`: content parsing helpers (`parse_content`, `serialize_content`, `replace_body`, `replace_title`, `has_title`). Single source of truth for Codecks content format.
- `_contract_error()` now accepts `retryable: bool` and `error_code: str` kwargs. `_call()` classifies errors: SetupError → not retryable, CliError → not retryable, ConnectionError/TimeoutError/OSError → retryable, other Exception → retryable.
- Cache metadata includes `stale_warning: True` and `cache_ttl_seconds` when age exceeds 80% of TTL.
- New MCP tool: `update_card_body(card_id, body)` — body-only edit preserving title.
- Tool count: 51 (43 core + 8 team)

**Step 2: No commit needed — memory is gitignored**
