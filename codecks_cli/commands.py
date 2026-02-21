"""
Command implementations for codecks-cli.
Each cmd_*() function receives an argparse.Namespace and handles one CLI command.

Business logic lives in client.py (CodecksClient). These thin wrappers
handle argparse → keyword args, format selection, and formatter dispatch.
"""

import sys

from codecks_cli import config
from codecks_cli.api import _mask_token, _safe_json_parse, dispatch, generate_report_token, query
from codecks_cli.client import CodecksClient, _normalize_dispatch_path
from codecks_cli.exceptions import CliError
from codecks_cli.formatters import (
    format_account_table,
    format_activity_table,
    format_card_detail,
    format_cards_csv,
    format_cards_table,
    format_conversations_table,
    format_decks_table,
    format_gdd_table,
    format_milestones_table,
    format_pm_focus_table,
    format_projects_table,
    format_standup_table,
    format_stats_table,
    format_sync_report,
    mutation_response,
    output,
)
from codecks_cli.gdd import (
    _revoke_google_auth,
    _run_google_auth_flow,
    fetch_gdd,
    parse_gdd,
    sync_gdd,
)
from codecks_cli.models import FeatureSpec, ObjectPayload

# ---------------------------------------------------------------------------
# Dry-run helper
# ---------------------------------------------------------------------------


def _dry_run_guard(action, details=""):
    """If dry-run mode is active, print what *would* happen and return True."""
    if not config.RUNTIME_DRY_RUN:
        return False
    msg = f"[DRY-RUN] {action}: {details}" if details else f"[DRY-RUN] {action}"
    print(msg, file=sys.stderr)
    return True


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

_client_instance = None


def _get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = CodecksClient(validate_token=False)
    return _client_instance


# ---------------------------------------------------------------------------
# Read commands
# ---------------------------------------------------------------------------


def cmd_query(ns):
    q = ObjectPayload.from_value(_safe_json_parse(ns.json_query, "query"), "query").data
    if config.RUNTIME_STRICT:
        root = q.get("_root")
        if not isinstance(root, list) or not root:
            raise CliError(
                "[ERROR] Strict mode: query payload must include non-empty '_root' array."
            )
    output(query(q), fmt=ns.format)


def cmd_account(ns):
    output(_get_client().get_account(), format_account_table, ns.format)


def cmd_decks(ns):
    output(_get_client().list_decks(), format_decks_table, ns.format)


def cmd_projects(ns):
    output(_get_client().list_projects(), format_projects_table, ns.format)


def cmd_milestones(ns):
    output(_get_client().list_milestones(), format_milestones_table, ns.format)


def cmd_cards(ns):
    fmt = ns.format
    result = _get_client().list_cards(
        deck=ns.deck,
        status=ns.status,
        project=ns.project,
        search=ns.search,
        milestone=ns.milestone,
        tag=ns.tag,
        owner=ns.owner,
        priority=getattr(ns, "priority", None),
        sort=ns.sort,
        card_type=ns.type,
        hero=ns.hero,
        hand_only=ns.hand,
        stale_days=getattr(ns, "stale", None),
        updated_after=getattr(ns, "updated_after", None),
        updated_before=getattr(ns, "updated_before", None),
        archived=ns.archived,
        include_stats=ns.stats,
    )
    if ns.stats:
        output(result["stats"], format_stats_table, fmt)
    else:
        output(result, format_cards_table, fmt, csv_formatter=format_cards_csv)


def cmd_card(ns):
    output(_get_client().get_card(ns.card_id), format_card_detail, ns.format)


# ---------------------------------------------------------------------------
# Mutation commands
# ---------------------------------------------------------------------------


def cmd_create(ns):
    if _dry_run_guard("create card", f"title='{ns.title}'"):
        return
    fmt = ns.format
    result = _get_client().create_card(
        ns.title,
        content=ns.content,
        deck=ns.deck,
        project=ns.project,
        severity=ns.severity,
        doc=ns.doc,
        allow_duplicate=getattr(ns, "allow_duplicate", False),
    )
    for w in result.get("warnings", []):
        print(f"[WARN] {w}", file=sys.stderr)
    detail = f"title='{ns.title}'"
    if result.get("deck"):
        detail += f", deck='{result['deck']}'"
    if result.get("doc"):
        detail += ", type=doc"
    mutation_response("Created", result["card_id"], detail, fmt=fmt)


def cmd_feature(ns):
    """Scaffold one Hero feature plus Code/Design/(optional Art) sub-cards."""
    if _dry_run_guard("scaffold feature", f"title='{ns.title}'"):
        return
    spec = FeatureSpec.from_namespace(ns)
    fmt = spec.format
    result = _get_client().scaffold_feature(
        spec.title,
        hero_deck=spec.hero_deck,
        code_deck=spec.code_deck,
        design_deck=spec.design_deck,
        art_deck=spec.art_deck,
        skip_art=spec.skip_art,
        description=spec.description,
        owner=spec.owner,
        priority=spec.priority,
        effort=spec.effort,
        allow_duplicate=spec.allow_duplicate,
    )
    if fmt == "table":
        lines = [
            f"Hero created: {result['hero']['id']} ({result['hero']['title']})",
            f"Sub-cards created: {len(result.get('subcards', []))}",
        ]
        for item in result.get("subcards", []):
            lines.append(f"  - [{item['lane']}] {item['id']}")
        if result.get("notes"):
            for note in result["notes"]:
                lines.append(f"[NOTE] {note}")
        print("\n".join(lines))
    else:
        output(result, fmt=fmt)


def cmd_update(ns):
    if _dry_run_guard("update card(s)", f"ids={ns.card_ids}"):
        return
    fmt = ns.format
    result = _get_client().update_cards(
        ns.card_ids,
        status=ns.status,
        priority=ns.priority,
        effort=ns.effort,
        deck=ns.deck,
        title=ns.title,
        content=ns.content,
        milestone=ns.milestone,
        hero=ns.hero,
        owner=ns.owner,
        tags=ns.tag,
        doc=ns.doc,
    )
    fields = result.get("fields", {})
    detail_parts = [f"{k}={v}" for k, v in fields.items()]
    if len(ns.card_ids) > 1:
        mutation_response(
            "Updated",
            details=f"{len(ns.card_ids)} card(s), " + ", ".join(detail_parts),
            data=result.get("data"),
            fmt=fmt,
        )
    else:
        mutation_response(
            "Updated", ns.card_ids[0], ", ".join(detail_parts), result.get("data"), fmt
        )


def cmd_archive(ns):
    if _dry_run_guard("archive card", ns.card_id):
        return
    result = _get_client().archive_card(ns.card_id)
    mutation_response("Archived", ns.card_id, data=result.get("data"), fmt=ns.format)


def cmd_unarchive(ns):
    if _dry_run_guard("unarchive card", ns.card_id):
        return
    result = _get_client().unarchive_card(ns.card_id)
    mutation_response("Unarchived", ns.card_id, data=result.get("data"), fmt=ns.format)


def cmd_delete(ns):
    if _dry_run_guard("delete card", ns.card_id):
        return
    result = _get_client().delete_card(ns.card_id)
    mutation_response("Deleted", ns.card_id, data=result.get("data"), fmt=ns.format)


def cmd_done(ns):
    if _dry_run_guard("mark done", f"{len(ns.card_ids)} card(s)"):
        return
    result = _get_client().mark_done(ns.card_ids)
    mutation_response(
        "Marked done", details=f"{len(ns.card_ids)} card(s)", data=result.get("data"), fmt=ns.format
    )


def cmd_start(ns):
    if _dry_run_guard("mark started", f"{len(ns.card_ids)} card(s)"):
        return
    result = _get_client().mark_started(ns.card_ids)
    mutation_response(
        "Marked started",
        details=f"{len(ns.card_ids)} card(s)",
        data=result.get("data"),
        fmt=ns.format,
    )


# ---------------------------------------------------------------------------
# Hand commands
# ---------------------------------------------------------------------------


def cmd_hand(ns):
    fmt = ns.format
    if not ns.card_ids:
        hand_cards = _get_client().list_hand()
        if not hand_cards:
            print("Your hand is empty.", file=sys.stderr)
            return
        output(
            {"cards": hand_cards, "stats": None},
            format_cards_table,
            fmt,
            csv_formatter=format_cards_csv,
        )
    else:
        if _dry_run_guard("add to hand", f"{len(ns.card_ids)} card(s)"):
            return
        result = _get_client().add_to_hand(ns.card_ids)
        mutation_response(
            "Added to hand", details=f"{len(ns.card_ids)} card(s)", data=result.get("data"), fmt=fmt
        )


def cmd_unhand(ns):
    if _dry_run_guard("remove from hand", f"{len(ns.card_ids)} card(s)"):
        return
    result = _get_client().remove_from_hand(ns.card_ids)
    mutation_response(
        "Removed from hand",
        details=f"{len(ns.card_ids)} card(s)",
        data=result.get("data"),
        fmt=ns.format,
    )


# ---------------------------------------------------------------------------
# Activity command
# ---------------------------------------------------------------------------


def cmd_activity(ns):
    result = _get_client().list_activity(limit=ns.limit)
    output(result, format_activity_table, ns.format)


def cmd_pm_focus(ns):
    """Show focused PM dashboard: blocked, in_review, hand, stale, and suggested."""
    stale_days = getattr(ns, "stale_days", 14) or 14
    report = _get_client().pm_focus(
        project=ns.project, owner=ns.owner, limit=ns.limit, stale_days=stale_days
    )
    output(report, format_pm_focus_table, ns.format)


def cmd_standup(ns):
    """Show daily standup summary: recently done, in progress, blocked, hand."""
    report = _get_client().standup(days=ns.days, project=ns.project, owner=ns.owner)
    output(report, format_standup_table, ns.format)


# ---------------------------------------------------------------------------
# Comment commands
# ---------------------------------------------------------------------------


def cmd_comment(ns):
    if _dry_run_guard("comment on card", ns.card_id):
        return
    fmt = ns.format
    card_id = ns.card_id
    selected = [bool(ns.thread), bool(ns.close), bool(ns.reopen)]
    if sum(selected) > 1:
        raise CliError("[ERROR] Use only one of --thread, --close, or --reopen.")
    client = _get_client()
    if ns.close:
        if ns.message:
            raise CliError("[ERROR] Do not provide a message with --close.")
        result = client.close_comment(ns.close, card_id)
        mutation_response("Closed thread", ns.close, "", result.get("data"), fmt)
    elif ns.reopen:
        if ns.message:
            raise CliError("[ERROR] Do not provide a message with --reopen.")
        result = client.reopen_comment(ns.reopen, card_id)
        mutation_response("Reopened thread", ns.reopen, "", result.get("data"), fmt)
    elif ns.thread:
        if not ns.message:
            raise CliError("[ERROR] Reply message is required.")
        result = client.reply_comment(ns.thread, ns.message)
        mutation_response("Replied to thread", ns.thread, "", result.get("data"), fmt)
    else:
        if not ns.message:
            raise CliError("[ERROR] Comment message is required.")
        result = client.create_comment(card_id, ns.message)
        mutation_response("Created thread on", card_id, "", result.get("data"), fmt)


def cmd_conversations(ns):
    output(_get_client().list_conversations(ns.card_id), format_conversations_table, ns.format)


# ---------------------------------------------------------------------------
# GDD commands
# ---------------------------------------------------------------------------


def cmd_gdd(ns):
    content = fetch_gdd(
        force_refresh=ns.refresh,
        local_file=ns.file,
        save_cache=ns.save_cache,
    )
    sections = parse_gdd(content)
    output(sections, format_gdd_table, ns.format)


def cmd_gdd_sync(ns):
    if ns.apply and _dry_run_guard("gdd-sync --apply", f"project='{ns.project}'"):
        return
    fmt = ns.format
    if not ns.project:
        from codecks_cli.cards import load_project_names

        available = [n for n in load_project_names().values()]
        hint = f" Available: {', '.join(available)}" if available else ""
        raise CliError(f"[ERROR] --project is required for gdd-sync.{hint}")
    content = fetch_gdd(
        force_refresh=ns.refresh,
        local_file=ns.file,
        save_cache=ns.save_cache,
    )
    sections = parse_gdd(content)
    report = sync_gdd(
        sections,
        ns.project,
        target_section=ns.section,
        apply=ns.apply,
        quiet=config.RUNTIME_QUIET,
    )
    output(report, format_sync_report, fmt)


def cmd_gdd_auth(ns):
    _run_google_auth_flow()


def cmd_gdd_revoke(ns):
    _revoke_google_auth()


# ---------------------------------------------------------------------------
# Token & raw API commands
# ---------------------------------------------------------------------------


def cmd_generate_token(ns):
    result = generate_report_token(ns.label)
    print(f"Report Token created: {_mask_token(result['token'])}")
    print("Full token saved to .env as CODECKS_REPORT_TOKEN")


def cmd_completion(ns):
    """Generate shell completion script for bash, zsh, or fish."""
    from codecks_cli.cli import build_parser

    shell = ns.shell
    parser = build_parser()

    # Extract subcommand names and their options from parser internals
    subcommands = []
    sub_options: dict[str, list[str]] = {}
    for action in parser._subparsers._actions:
        if hasattr(action, "_name_parser_map"):
            for name, subparser in sorted(action._name_parser_map.items()):
                subcommands.append(name)
                opts: list[str] = []
                for act in subparser._actions:
                    opts.extend(s for s in act.option_strings if s.startswith("--"))
                sub_options[name] = opts
            break

    cmds_str = " ".join(subcommands)
    global_opts = "--format --strict --dry-run --quiet --verbose --version --help"

    if shell == "bash":
        cases = []
        for name in subcommands:
            if sub_options[name]:
                cases.append(f'        {name}) opts="{" ".join(sub_options[name])}" ;;')
        cases_block = "\n".join(cases)
        print(
            f"_codecks_cli_complete() {{\n"
            f'    local cur="${{COMP_WORDS[COMP_CWORD]}}"\n'
            f'    local prev="${{COMP_WORDS[COMP_CWORD-1]}}"\n'
            f'    local commands="{cmds_str}"\n'
            f'    local global_opts="{global_opts}"\n'
            f'    if [ "$COMP_CWORD" -eq 1 ]; then\n'
            f'        COMPREPLY=($(compgen -W "$commands $global_opts" -- "$cur"))\n'
            f"        return\n"
            f"    fi\n"
            f'    local cmd="${{COMP_WORDS[1]}}"\n'
            f'    local opts=""\n'
            f'    case "$cmd" in\n'
            f"{cases_block}\n"
            f"    esac\n"
            f'    COMPREPLY=($(compgen -W "$opts $global_opts" -- "$cur"))\n'
            f"}}\n"
            f"complete -F _codecks_cli_complete codecks-cli\n"
            f"complete -F _codecks_cli_complete codecks_api.py"
        )
    elif shell == "zsh":
        desc_lines = []
        for name in subcommands:
            desc_lines.append(f"        '{name}:{name} command'")
        descs = "\n".join(desc_lines)
        print(
            f"#compdef codecks-cli codecks_api.py\n"
            f"\n"
            f"_codecks_cli() {{\n"
            f"    local -a commands\n"
            f"    commands=(\n"
            f"{descs}\n"
            f"    )\n"
            f'    _describe "command" commands\n'
            f"}}\n"
            f"\n"
            f'_codecks_cli "$@"'
        )
    elif shell == "fish":
        lines = [
            "# Fish completions for codecks-cli",
            f"set -l commands {cmds_str}",
            f'complete -c codecks-cli -n "not __fish_seen_subcommand_from $commands" '
            f'-a "{cmds_str}"',
        ]
        for name in subcommands:
            if sub_options[name]:
                for opt in sub_options[name]:
                    flag = opt.lstrip("-")
                    lines.append(
                        f'complete -c codecks-cli -n "__fish_seen_subcommand_from {name}" -l {flag}'
                    )
        print("\n".join(lines))


def cmd_dispatch(ns):
    path = _normalize_dispatch_path(ns.path)
    payload = ObjectPayload.from_value(
        _safe_json_parse(ns.json_data, "dispatch data"), "dispatch data"
    ).data
    if config.RUNTIME_STRICT:
        if "/" not in path:
            raise CliError(
                "[ERROR] Strict mode: dispatch path should include action "
                "segment, e.g. cards/update."
            )
        if not payload:
            raise CliError("[ERROR] Strict mode: dispatch payload cannot be empty.")
    result = dispatch(path, payload)
    output(result, fmt=ns.format)
