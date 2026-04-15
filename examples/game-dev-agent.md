# Game Dev Agent Example

Real-world example showing how to extend the base codecks-cli PM workflow for
game development with Art, Audio, Blueprint, and Design lanes.

This is how one team uses codecks-cli to manage a 2D game project. Adapt the
patterns to your own project — the base playbook (`codecks_cli/pm_playbook.md`)
covers the universal patterns; this file shows the game-dev additions on top.

## Additional Lanes

Beyond the default Code and Design lanes, game projects typically need:

- **Art** — sprites, backgrounds, UI elements, VFX, particle effects
- **Audio** — sound effects, music, voiceover
- **Blueprint** — visual scripting wiring docs (Unreal Engine specific)

```bash
codecks-cli feature "Brewing System" \
  --hero-deck Features \
  --code-deck Coding \
  --design-deck "Game Design" \
  --art-deck Art \
  --audio-deck Audio \
  --priority b \
  --agent
```

## Sub-Card Content Templates

After scaffolding, enrich each sub-card with domain-specific content.

### Design cards

- Feature-specific open design questions (not generic "define player feel")
- Interaction flow decisions with concrete options
- Difficulty and tuning parameters
- Tone guidance from the design document

### Art cards

```
## Asset Overview (1-2 sentences)
## Assets Needed
### Sprites (name, size px, animation frames)
### Backgrounds (name, resolution)
### UI Elements (name, states: normal/hover/pressed)
### VFX / Particles (name, trigger)
### References (style, color palette)
```

### Audio cards

- Named sound deliverable checklist with `- []` checkboxes
- Per-sound mood and material description (wood, ceramic, paper — not digital)
- Reference to the game's tone (cozy, warm, analog)
- Guidance on what NOT to do (no harsh failure sounds, no jarring alerts)

### Code cards

```
## Deliverables (checkbox list)
## Files Modified
## Blueprint Exposure (new properties/functions exposed to visual scripting)
## Verification Checklist
```

## Feature Decomposition Rules

- Minimum: Hero + Code + Design
- Add Art if the feature changes visuals, UI, or assets
- Add Audio if the feature changes sound, music, or feedback
- Add Blueprint only when C++ implementation is done and visual scripting
  wiring is needed
- State why a lane was skipped

## Hand Management for Multi-Discipline Features

The hand should contain ALL cards for the ACTIVE feature:

```bash
# Switch to a new feature
codecks-cli cards --search "Brewing" --ids-only | codecks-cli hand --stdin --agent

# Clear old feature cards
codecks-cli cards --hand --ids-only | codecks-cli unhand --stdin --agent
```

When a sub-card is done, remove it from hand but keep the remaining feature
cards until the entire feature is complete.

## GDD Sync Workflow

If you maintain a Game Design Document (Google Docs or local file):

```bash
codecks-cli gdd --agent                        # parse GDD, show features
codecks-cli gdd-sync --project "My Game" --agent  # sync to Codecks
```

Four surfaces to keep aligned: GDD, Codecks cards, architecture docs, code.
Check for drift: GDD build status vs card status, GDD features vs card
titles, done cards vs GDD completion markers.

## Team Roles

Map team members to lane ownership:

- Programmer: Code + Blueprint cards
- Designer: Design + Hero cards
- Artist: Art cards
- Audio designer: Audio cards

Use `codecks-cli partition --by owner --agent` to see work distribution across
the team.
