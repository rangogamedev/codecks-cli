# PM Skill

Use this skill for day-to-day Codecks project management with a CLI-first
workflow.

## Startup

Always begin with:

```bash
codecks-cli agent-init --agent
```

This gives you the project context, tag registry, and lane registry in one call.

## Default Workflow

1. Use `standup`, `pm-focus`, or `overview` to scope the problem.
2. Use `cards` to get the exact target set.
3. Use `card` when you need detail on one item.
4. Mutate with the smallest command that solves the task.
5. Verify with a follow-up read.

## Preferred Commands

```bash
codecks-cli standup --agent
codecks-cli pm-focus --agent
codecks-cli cards --status started --agent
codecks-cli card <uuid> --agent
codecks-cli update <uuid> --status done --agent
```

## Batch Patterns

```bash
codecks-cli cards --status blocked --ids-only | codecks-cli done --stdin --agent
codecks-cli cards --deck Backlog --ids-only | codecks-cli hand --stdin --agent
codecks-cli cards --deck Code --status started --ids-only | codecks-cli update --stdin --status in_review --agent
```

Use `@last` when the previous listing already contains the exact target set.

## Safety Rules

- Use full UUIDs for mutations.
- Re-read after every mutation workflow.
- Do not set `dueAt`.
- Do not change doc-card status, priority, or effort.
- Explain skipped Art or Audio lanes when decomposing features.

## When To Use MCP

Prefer MCP only when you need:

- `session_start()` in an MCP-native setup
- `find_and_update()`
- claim/release/delegate coordination
- snapshot-cached repeated reads

Otherwise, stay on the CLI for smaller context and simpler workflows.
