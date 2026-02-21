# PM Session Playbook (MCP)

Agent-agnostic guide for running PM sessions on Codecks via MCP tools.
Any AI agent connected to the Codecks MCP server can follow this playbook.

## Session Start

1. Call `standup` for an immediate snapshot: recently done, in-progress, blocked, hand.
2. Call `get_workflow_preferences` to load the user's observed patterns. If `found` is true, follow those patterns silently.
3. Call `get_account` to verify authentication.

If authentication fails (response has `ok: false, type: "setup"`), stop and ask the user to refresh their token or run setup.

## Core Execution Loop

For every PM request, follow this loop:

1. **Scope** — Identify the target set by project/deck/status/tag/owner/search.
2. **Fetch** — Query a minimal list first: `list_cards` with filters.
3. **Select** — Resolve full 36-character UUIDs from the list before any mutation.
4. **Mutate** — Apply the smallest change set needed.
5. **Verify** — Re-read affected cards (`get_card`) and confirm expected state.
6. **Report** — Return a concise summary + any unresolved blockers.

Never skip step 5 for mutation workflows.

## Feature Decomposition

Every feature starts as one Hero card. Evaluate these lanes:

- **Code** — implementation tasks
- **Art** — visual/content/asset tasks
- **Design** — feel, balance, economy, player-facing tuning

Minimum output: one Hero + one Code sub-card + one Design sub-card. Add Art if visuals are impacted. If a lane is skipped, state why.

Use `scaffold_feature` to create a Hero with sub-cards in one operation:

```
scaffold_feature(
    title="Feature Name",
    hero_deck="Features",
    code_deck="Code",
    design_deck="Design",
    art_deck="Art",        # omit + skip_art=True if no visuals
    description="Player outcome and success criteria",
    owner="OwnerName",
    priority="b"
)
```

## Hand Management

The hand is the user's personal work queue (daily focus list).

- `list_hand` — see current hand cards in priority order
- `add_to_hand(card_ids=[...])` — queue cards for today
- `remove_from_hand(card_ids=[...])` — remove completed/deprioritized cards

Typical flow:
1. `list_cards(status="not_started", sort="priority")` — find candidates
2. `add_to_hand(card_ids=[...])` — queue selected cards
3. `mark_started(card_ids=[...])` — begin work
4. `list_hand` — verify hand state

## Dashboard Shortcuts

Use these instead of assembling dashboards from raw card lists:

- **`standup`** — recently done, in-progress, blocked, hand. Use `days` param for lookback.
- **`pm_focus`** — sprint health: blocked, unassigned, stale, suggested next cards. Use `stale_days` param.

Both accept `project` and `owner` filters.

## Filtering & Search

```
list_cards(status="started,blocked")         # comma-separated multi-value
list_cards(priority="a,b")                   # high-priority cards
list_cards(owner="none", status="not_started") # unassigned backlog
list_cards(stale_days=14, status="started")  # stale started cards
list_cards(search="inventory")               # title/content search
list_cards(hero="<uuid>")                    # sub-cards of a hero
```

Pagination: default 50 cards. Use `limit` and `offset` to page through large sets.

## Mutation Patterns

```
update_cards(card_ids=["<uuid>"], status="started")
update_cards(card_ids=["<uuid>"], priority="a", owner="Alice")
mark_done(card_ids=["<uuid1>", "<uuid2>"])
mark_started(card_ids=["<uuid1>"])
create_card(title="Bug: ...", deck="Bugs", content="Description")
```

For bulk updates, batch ~10 at a time and verify between batches.

## Comments

- `create_comment(card_id, message)` — new thread
- `reply_comment(thread_id, message)` — reply to existing thread
- `close_comment(thread_id, card_id)` — resolve a thread
- `list_conversations(card_id)` — see all threads and find thread IDs

## Safety Rules

These are non-negotiable:

- **Full UUIDs only** — all mutation tools require 36-character UUIDs. Short IDs return 400 errors.
- **Never set `dueAt`** — due dates are a paid-only feature. The `stale_days`, `updated_after`, and `updated_before` filters only read existing timestamps.
- **Doc card limitations** — doc cards cannot have `status`, `priority`, or `effort`. Only set owner, tags, milestone, deck, title, content, or hero.
- **Content replaces fully** — `content` in `update_cards` replaces the entire card body. Keep the title as the first line.
- **Never close a Hero** before checking that all sub-cards across Code/Art/Design are done.
- **Never mutate from a stale list** — refresh the card selection before applying changes.
- **Duplicate protection** — `create_card` and `scaffold_feature` check for duplicate titles. Use `allow_duplicate=True` to bypass when intentional.

## Token Efficiency

Minimize API calls and response sizes:

- Use `list_cards` filters (status, deck, owner, tag) to narrow results server-side.
- Use `get_card(include_content=False)` when you only need metadata (status, priority, owner).
- Use `get_card(include_conversations=False)` when you don't need comment threads.
- Use `list_decks(include_card_counts=False)` when you only need deck names.
- Use `pm_focus` or `standup` for dashboards instead of assembling from raw card lists.
- Rate limit: 40 requests per 5 seconds. HTTP 429 triggers automatic retries for reads.

## Workflow Learning

Observe the user's patterns during the session:

- **Card selection**: Do they pick cards themselves, or ask for suggestions?
- **Work style**: Finish in-progress before starting new? Or juggle multiple?
- **Hand usage**: Actively manage their hand, or ignore it?
- **Focus area**: Specific projects, decks, or tags they gravitate toward?
- **Triage style**: Priority-first? Effort-first?
- **Blocked cards**: Want immediate escalation or quiet tracking?
- **Communication**: Brief updates or detailed breakdowns?

At session end, call `save_workflow_preferences` with a list of observed pattern strings. Only record patterns seen at least twice or explicitly stated by the user. These preferences are loaded at the start of future sessions via `get_workflow_preferences`.

These are observations, not rules. If the user changes behavior, update the preferences. Never say "but last time you preferred X."

## Error Handling

Check the `ok` field in every response:

- `ok: false, type: "setup"` — token expired or missing. Ask user to re-authenticate.
- `ok: false, type: "error"` — validation or API error. Fix arguments and retry once.
- HTTP transient errors (429/502/503/504) have automatic retries for reads. For writes, re-check state before retrying.

## Recommended Workflows by Intent

| Intent | Tool Call |
|---|---|
| Daily standup | `standup()` or `standup(project="Tea Shop")` |
| Sprint health | `pm_focus()` or `pm_focus(stale_days=7)` |
| Triage | `list_cards(status="started,blocked", sort="priority")` |
| Stale sweep | `list_cards(status="started", stale_days=14)` |
| Unassigned work | `list_cards(owner="none", status="not_started")` |
| Owner review | `list_cards(owner="Alice", status="started")` |
| Priority focus | `list_cards(priority="a,b", status="started")` |
| Milestone review | `list_cards(milestone="MVP")` |
| Cleanup | `list_cards(search="term")`, then `update_cards` |

## Delivery Format

When reporting results to the user:

- **What changed**: explicit card IDs + new status/priority/owner
- **What was verified**: which cards were re-read for confirmation
- **What is blocked**: token/setup/API/data issues needing user input
