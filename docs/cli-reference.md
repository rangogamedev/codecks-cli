# CLI Reference

Full command reference for codecks-cli. For installation and quickstart, see [README.md](../README.md).

Run commands with `codecks-cli <command>` (or `py codecks_api.py <command>` if not installed).

## Commands Overview

| Command | Description |
|---------|-------------|
| `account` | Show current account info |
| `cards` | List cards with filtering, stats, pagination |
| `card` | Single card details with sub-cards |
| `decks` | List all decks with card counts |
| `projects` | List all projects |
| `milestones` | List all milestones |
| `tags` | List project-level tags |
| `activity` | Recent activity feed |
| `standup` | Daily standup summary |
| `pm-focus` | Sprint health dashboard |
| `overview` | Compact project overview (aggregate counts) |
| `create` | Create a card |
| `feature` | Scaffold Hero + sub-cards |
| `split-features` | Batch-split feature cards into discipline sub-cards |
| `update` | Update card properties |
| `done` | Mark cards as done |
| `start` | Mark cards as started |
| `hand` | View or add cards to your hand |
| `unhand` | Remove cards from hand |
| `comment` | Add, reply, close, or reopen comment threads |
| `conversations` | List all comment threads on a card |
| `archive` / `remove` | Archive cards (reversible) |
| `unarchive` | Restore archived cards |
| `delete` | Permanently delete a card (requires `--confirm`) |
| `setup` | Interactive setup wizard |
| `generate-token` | Create a report token |
| `completion` | Shell completions (bash/zsh/fish) |
| `gdd` | View parsed GDD tasks |
| `gdd-sync` | Sync GDD tasks to Codecks cards |
| `gdd-auth` | Authorize Google Drive access |
| `gdd-revoke` | Revoke Google authorization |
| `query` | Raw GraphQL query |
| `dispatch` | Raw API mutation |

## Reading Data

```bash
# Account info
codecks-cli account

# List all cards
codecks-cli cards

# Filter cards
codecks-cli cards --deck "Backlog"
codecks-cli cards --status started
codecks-cli cards --project "My Project"
codecks-cli cards --search "inventory"
codecks-cli cards --owner "Thomas"
codecks-cli cards --owner none               # unassigned cards
codecks-cli cards --milestone "Sprint 1"

# Multi-value filters (comma-separated)
codecks-cli cards --status started,blocked    # started OR blocked
codecks-cli cards --priority a,b              # high or medium priority
codecks-cli cards --priority null             # cards with no priority set

# Date filters and stale detection
codecks-cli cards --stale 14                  # not updated in 14 days
codecks-cli cards --updated-after 2026-01-01
codecks-cli cards --updated-before 2026-02-01
codecks-cli cards --status started --stale 7  # combine with other filters

# Combine filters
codecks-cli cards --project "My Project" --status started --search "bug"

# Card statistics (counts by status, priority, deck, owner)
codecks-cli cards --stats
codecks-cli cards --project "My Project" --stats

# Single card details (includes sub-cards, severity, hero parent)
codecks-cli card <card-id>

# Decks (with card counts), projects, milestones
codecks-cli decks
codecks-cli projects
codecks-cli milestones

# Recent activity (shows card titles)
codecks-cli activity
codecks-cli activity --limit 50
```

## Daily Standup

```bash
# Default: last 2 days of activity
codecks-cli standup --format table

# Look back further
codecks-cli standup --days 5 --format table

# Filter by project or owner
codecks-cli standup --project "My Project" --format table
codecks-cli standup --owner "Thomas" --format table
```

Standup sections: **Done** (recently completed), **In Progress** (started/in-review), **Blocked**, **In Hand** (minus completed).

## PM Focus (Sprint Health)

```bash
# Sprint health overview
codecks-cli pm-focus --format table

# Filter by project, customize stale threshold
codecks-cli pm-focus --project "My Project" --stale-days 7 --format table
```

PM Focus sections: **Blocked**, **Unassigned** (started cards with no owner), **Started**, **In Review**, **Stale** (not updated in N days).

## Creating Cards

```bash
# Simple card (lands in Inbox by default)
codecks-cli create "Fix login bug"

# Card with description and severity
codecks-cli create "Server crash on startup" --content "Happens after the latest deploy" --severity critical

# Create into a specific deck or project
codecks-cli create "Refactor save system" --deck "Backlog"
codecks-cli create "New feature idea" --project "My Project"

# Create as sub-card
codecks-cli create "Sub-task" --parent <parent-card-id>

# Bypass duplicate-title protection
codecks-cli create "Fix login bug" --allow-duplicate
```

Duplicate-title safety: exact title matches fail fast to prevent accidents. Use `--allow-duplicate` to override. Near matches show as warnings only.

## Feature Scaffolding (Hero + Sub-Cards)

```bash
codecks-cli feature "Inventory 2.0" \
  --hero-deck "Features" \
  --code-deck "Code" \
  --design-deck "Design" \
  --art-deck "Art" \
  --priority a --effort 5

# Non-visual features (skip art)
codecks-cli feature "Economy Tuning" \
  --hero-deck "Features" \
  --code-deck "Code" \
  --design-deck "Design" \
  --skip-art
```

Transaction safety: if scaffolding fails mid-way, created cards are rolled back (archived). Severity levels: `critical`, `high`, `low`, or `null`.

## Updating Cards

```bash
# Status, priority, effort
codecks-cli update <id> --status started
codecks-cli update <id> --priority a          # a=high, b=medium, c=low, null=remove
codecks-cli update <id> --effort 5

# Move, rename, re-describe
codecks-cli update <id> --deck "In Progress"
codecks-cli update <id> --title "Better name"
codecks-cli update <id> --content "Updated description"

# Owner and tags
codecks-cli update <id> --owner "Thomas"
codecks-cli update <id> --owner none          # unassign
codecks-cli update <id> --tags "bug,urgent"
codecks-cli update <id> --tags none

# Milestone and hero
codecks-cli update <id> --milestone "Sprint 1"
codecks-cli update <id> --milestone none
codecks-cli update <id> --hero <parent-id>
codecks-cli update <id> --hero none           # detach

# Combine multiple updates
codecks-cli update <id> --status started --priority a --effort 3
```

## Hand Management

```bash
codecks-cli hand                  # view cards in your hand
codecks-cli hand <id1> <id2>      # add cards
codecks-cli unhand <id1> <id2>    # remove cards
```

## Comments

```bash
codecks-cli comment <card-id> "This needs review"
codecks-cli comment <card-id> "Good point" --thread <comment-id>
codecks-cli comment <card-id> --close <comment-id>
codecks-cli comment <card-id> --reopen <comment-id>
codecks-cli conversations <card-id>
```

## Bulk Status Changes

```bash
codecks-cli done <id1> <id2> <id3>
codecks-cli start <id1> <id2>
```

## Archiving and Deleting

```bash
codecks-cli archive <id>          # reversible
codecks-cli remove <id>           # same as archive
codecks-cli unarchive <id>        # restore
codecks-cli delete <id> --confirm # permanent (requires --confirm)
```

## GDD Sync (Game Design Document)

Read a Game Design Document and sync tasks to Codecks. Sources: Google Doc (public or private), local markdown file, or stdin.

### Setup

Add your Google Doc URL to `.env` (share with "Anyone with the link can view"):

```env
GDD_GOOGLE_DOC_URL=https://docs.google.com/document/d/your-doc-id/edit
```

### GDD Format

```markdown
## Core Gameplay
- [P:a E:8] Implement day/night cycle
- [P:a E:5] Save/load system
  - Auto-save every 5 minutes
  - Manual save slots
- [P:b E:3] Inventory drag & drop
```

Tags: `[P:a]` = priority (a/b/c), `[E:5]` = effort, `[P:a E:5]` = both. All optional.

### Commands

```bash
codecks-cli gdd --format table                                    # view parsed tasks
codecks-cli gdd --refresh --format table                          # re-fetch from Google
codecks-cli gdd --file "my_gdd.md" --format table                 # local file
codecks-cli gdd-sync --project "My Project"                       # dry-run
codecks-cli gdd-sync --project "My Project" --apply               # create cards
codecks-cli gdd-sync --project "My Project" --section "Core" --apply  # one section
```

### Private Google Docs (OAuth2)

One-time setup (~5 minutes, free):

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) > Create project
2. Enable **Google Drive API** (APIs & Services > Library)
3. Create **OAuth 2.0 Client ID** (Desktop app type)
4. Add to `.env`:
   ```env
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   ```
5. Run `codecks-cli gdd-auth` (opens browser)

Revoke later: `codecks-cli gdd-revoke`

Alternatives (no OAuth): export as `.md` and use `--file`, or `--file -` for stdin piping.

## Output Formats

All commands default to JSON. Add `--format table` for human-readable or `--format csv` for spreadsheets.

```bash
codecks-cli cards                     # JSON (default)
codecks-cli cards --format table      # human-readable
codecks-cli cards --format csv        # spreadsheet
codecks-cli cards --stats --format table
```

### Example Table Output

```
Status         Pri   Eff  Owner      Deck              Mstone     Title                                ID
------------------------------------------------------------------------------------------------------------
not_started    a     8    Thomas     Core Systems      MVP        Implement save/load system           abc12345-...
started        b     3    -          Tasks             -          Fix inventory drag & drop            def67890-...
done           a     5    Alice      Backlog           Beta       Database migration                   ghi24680-...

Total: 3 cards
```

### Example Stats Output

```
Total cards: 38
Total effort: 159  Avg effort: 5.3

By Status:
  done               8
  not_started        25
  started            5

By Priority:
  a (high)           20
  b (medium)         11
  c (low)            4
  none               3
```

## Global Flags

| Flag | Description |
|------|-------------|
| `--format json\|table\|csv` | Output format (default: json) |
| `--json` | Force JSON output |
| `--agent` | Agent mode: JSON + suppress warnings + strict envelope |
| `--strict` | Fail-fast mode for raw API workflows |
| `--dry-run` | Preview mutations without executing |
| `--quiet` / `-q` | Suppress confirmations and warnings |
| `--verbose` / `-v` | Enable HTTP request logging |
| `--version` | Show version and exit |

Short aliases: `-d` (deck), `-s` (status), `-p` (priority), `-S` (search), `-e` (effort), `-c` (content).

## Raw API Calls

```bash
codecks-cli query '{"_root": [{"account": ["name", "id"]}]}'
codecks-cli dispatch cards/update '{"id": "card-uuid", "status": "done"}'
```

## Python API

```python
from codecks_cli import CodecksClient

client = CodecksClient()  # validates token on init

# List cards with filters
cards = client.list_cards(status="started", sort="priority")

# Create a card
result = client.create_card(title="Fix login bug", deck="Backlog")

# Update cards
client.update_cards(card_ids=["abc-123"], status="done", priority="a")

# Standup report
report = client.standup(days=3, project="My Project")
```

### 33 Methods

| Category | Methods |
|----------|---------|
| **Read** | `get_account`, `list_cards`, `get_card`, `list_decks`, `list_projects`, `list_milestones`, `list_tags`, `list_activity`, `pm_focus`, `standup`, `prefetch_snapshot` |
| **Hand** | `list_hand`, `add_to_hand`, `remove_from_hand` |
| **Mutations** | `create_card`, `update_cards`, `mark_done`, `mark_started`, `archive_card`, `unarchive_card`, `delete_card`, `scaffold_feature`, `split_features` |
| **Comments** | `create_comment`, `reply_comment`, `close_comment`, `reopen_comment`, `list_conversations` |
| **Admin** | `create_project`, `create_deck`, `create_milestone`, `create_tag`, `archive_deck_admin` |
| **Raw API** | `raw_query`, `raw_dispatch` |

All methods use keyword-only arguments and return `dict[str, Any]`.
