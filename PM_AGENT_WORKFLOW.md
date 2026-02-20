# PM Agent Workflow (No Journey)

This repository currently uses a **no-Journey** PM workflow for Codecks automation.

## Core Principle
- The agent does not rely on Codecks Journeys.
- The agent manually creates Hero cards and decomposes them into sub-cards.
- The agent routes sub-cards to the correct decks/categories.
- Preferred command for this flow: `feature` scaffold command.

## Feature Contract
For each player-facing feature:
1. Create one Hero card.
2. Evaluate and create sub-cards for:
   - Code
   - Art (if visuals/content are impacted)
   - Design (feel/economy/balance/playtest tuning)
3. Link each sub-card to Hero using `--hero <hero_id>`.
4. Route each sub-card to its deck with `--deck`.
5. Verify linkage/routing before reporting done.

## Suggested Deck Mapping
- Code -> implementation deck
- Art -> art/content deck
- Design -> game design/balance deck

## Required Verification
- `py codecks_api.py cards --hero <hero_id> --format table`
- `py codecks_api.py card <hero_id> --format table`

## Fast Path (recommended)

```bash
py codecks_api.py feature "<Feature Title>" \
  --hero-deck "<Hero Deck>" \
  --code-deck "<Code Deck>" \
  --design-deck "<Design Deck>" \
  --art-deck "<Art Deck>"
```

Use `--skip-art` when visuals/content are not impacted.

## Safety Rules
- Use full UUIDs for all mutation commands.
- Never close Hero without checking Code/Art/Design lane coverage.
- Keep title as first line when using `--content`.
- For doc cards, do not set status/priority/effort.
