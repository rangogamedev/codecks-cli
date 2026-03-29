# Plan: Fix Archived/Deleted Project Data Leaking Into Results

## Problem

The codecks-cli fetches cards, decks, and projects from Codecks.io but does not account for project-level archival status. Deleted or archived projects still appear in results because:

1. Card queries filter by card-level `visibility` only, not project status.
2. The `list_decks()` query fetches `account.decks` with no filtering — including decks from archived projects and decks where `isDeleted` is true.
3. Project discovery (`_build_project_map()`) groups all returned decks by `projectId` with no archive check.
4. The setup wizard stores every discovered project UUID in `.env` without checking archival status.

## Codecks API Context

The Codecks API (documented at `https://manual.codecks.io/api-reference/`) exposes three project relations on the `account` model:

- `projects` — active projects only
- `archivedProjects` — archived projects only
- `anyProjects` — everything (active + archived)

Similarly for decks: `decks` vs `anyDecks`.

The `deck` model has an `isDeleted` boolean field. The `project` model exists as a first-class entity with its own fields and relations.

The CLI currently queries `account.decks` (which may or may not include archived-project decks depending on API behavior) and never queries `account.projects` or `account.archivedProjects` directly.

All API reads go through `POST https://api.codecks.io/` with a JSON query body. The query language supports filtering via `{"fieldName": value}` or `{"fieldName": {"op": "...", "value": ...}}`.

## Files to Change

All paths relative to repo root.

### `codecks_cli/cards.py`

This is the primary file. Key functions:

| Function | Line | What it does now | What needs to change |
|---|---|---|---|
| `list_decks()` | ~79 | Queries `account.decks` with fields `title, id, projectId`. No filtering. Result is cached. | Add `isDeleted` to requested fields. Filter out decks where `isDeleted` is true. Consider also requesting the `project` relation on each deck to check project archival, OR maintain a separate set of archived project IDs (see `_get_archived_project_ids` below). |
| `list_cards()` | ~89 | Builds card query with `visibility: "default"`. Project filtering is client-side via deck IDs. | After fetching cards, exclude any whose `deckId` maps to an archived project or deleted deck. This should happen automatically if `list_decks()` is fixed, since `get_project_deck_ids()` and the project filter both derive from `list_decks()`. |
| `_build_project_map()` | ~272 | Groups all decks by `projectId`, assigns names from `.env`. No archive awareness. | Skip decks belonging to archived projects. Skip decks where `isDeleted` is true. |
| `list_projects()` | ~397 | Calls `_build_project_map()` and formats output. | Should automatically benefit from `_build_project_map()` fixes. |
| `list_activity()` | ~370 | Queries `account.activities`. No project filtering. | Consider filtering out activities whose associated card/deck belongs to an archived project. Lower priority — address after core fix. |

**New helper to add** — `_get_archived_project_ids()`:

```python
def _get_archived_project_ids():
    """Return a set of project IDs that are archived."""
    if "archived_project_ids" in config._cache:
        return config._cache["archived_project_ids"]
    q = {"_root": [{"account": [{"archivedProjects": ["id"]}]}]}
    result = query(q)
    ids = set()
    for _key, proj in result.get("project", {}).items():
        pid = proj.get("id")
        if pid:
            ids.add(pid)
    config._cache["archived_project_ids"] = ids
    return ids
```

This makes one extra API call (cached) to know which projects are archived so decks and cards from those projects can be excluded.

### `codecks_cli/setup_wizard.py`

| Function | Line | What needs to change |
|---|---|---|
| `_setup_discover_projects()` | ~22 | After discovering projects from decks, cross-reference against `_get_archived_project_ids()` and exclude them. Or query `account.projects` (active only) directly to get the list of project IDs to offer the user. |

### `codecks_cli/client.py`

The `CodecksClient` class wraps the functions in `cards.py`. Changes should flow through automatically, but verify:

- `list_cards()` (~191) — delegates to `cards.list_cards()`. Should inherit fix.
- `list_decks()` (~434) — delegates to `cards.list_decks()`. Should inherit fix.
- `list_projects()` (~469) — delegates to `cards.list_projects()`. Should inherit fix.

Check line ~295 where there's a `card_filter = json.dumps({"visibility": "default"})` — this is in a different method context; verify it's also covered.

### `codecks_cli/mcp_server/_tools_read.py`

MCP tools call through to `CodecksClient`. No direct changes expected, but verify the `list_cards`, `list_decks`, and `list_projects` tools return correct results after the fix.

### `codecks_cli/config.py`

No changes needed. The `_cache` dict is already available for storing archived project IDs.

## Implementation Steps

### Step 1: Add archived project detection

In `codecks_cli/cards.py`, add the `_get_archived_project_ids()` helper function described above. Place it near the other query helpers (around line 80).

### Step 2: Fix `list_decks()` to exclude deleted decks and archived-project decks

```python
def list_decks():
    if "decks" in config._cache:
        return config._cache["decks"]
    q = {"_root": [{"account": [{"decks": ["title", "id", "projectId", "isDeleted"]}]}]}
    result = query(q)
    warn_if_empty(result, "deck")

    # Filter out deleted decks and decks from archived projects
    archived_pids = _get_archived_project_ids()
    result["deck"] = {
        k: v for k, v in result.get("deck", {}).items()
        if not v.get("isDeleted")
        and _get_field(v, "project_id", "projectId") not in archived_pids
    }

    config._cache["decks"] = result
    return result
```

This is the single most impactful change. Since `list_cards()` resolves projects via `list_decks()`, and `_build_project_map()` iterates over decks from `list_decks()`, fixing the deck query fixes the downstream cascade.

### Step 3: Verify `_build_project_map()` no longer includes archived projects

After Step 2, `_build_project_map()` should automatically skip archived projects because those decks are no longer in the result set. Verify this is the case. No code change should be needed here.

### Step 4: Fix the setup wizard

In `setup_wizard.py`, `_setup_discover_projects()`, after building `project_decks` from deck data, filter out archived project IDs:

```python
from codecks_cli.cards import _get_archived_project_ids

archived = _get_archived_project_ids()
project_decks = {pid: titles for pid, titles in project_decks.items() if pid not in archived}
```

### Step 5: Add `--include-archived-projects` flag (optional enhancement)

In `cli.py`, add an optional flag to `cards`, `decks`, and `projects` commands that passes through to allow including archived project data when explicitly requested. This preserves the ability to see old data when needed.

### Step 6: Update tests

The test suite has 627 tests in `tests/`. Key test files to update:

- Tests for `list_decks()` — add test with `isDeleted: true` decks and verify they're excluded
- Tests for `list_cards()` with project filter — add test where some decks belong to archived projects
- Tests for `_build_project_map()` — verify archived projects don't appear
- Tests for setup wizard — verify archived projects are skipped during discovery

Since tests mock the API (no live calls), you'll need to add mock responses that include decks with `isDeleted: true` and projects in the archived set.

## Validation

After making changes:

```bash
# Run the full test suite
python -m pytest tests/ -v

# Run type checking
python -m mypy codecks_cli/

# Run linting
python -m ruff check codecks_cli/

# Manual smoke test (requires live tokens)
codecks-cli projects --format table
codecks-cli decks --format table
codecks-cli cards --format table
```

Verify that archived/deleted projects no longer appear in any of these outputs.

## Risk Notes

- The `_get_archived_project_ids()` call adds one extra API request per CLI invocation (cached after first call). This is within the 40 req/5s rate limit.
- The `isDeleted` field on decks is documented in the API reference but the CLI has never requested it. It should work, but test with a real account first.
- The `account.archivedProjects` relation is documented in the API reference. If it behaves unexpectedly (e.g., returns empty for free-tier accounts), the fix degrades gracefully — it just means no projects get excluded, which is the current behavior.
- Cards that were in archived projects but individually have `visibility: "default"` will no longer appear. This is the desired behavior but could surprise users who expect to see all their cards regardless of project status.
