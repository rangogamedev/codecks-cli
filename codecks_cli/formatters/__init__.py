"""Output formatting package for codecks-cli.

Re-exports all public names so consumers can do:
    from codecks_cli.formatters import format_cards_table
"""

from codecks_cli.formatters._activity import (
    format_activity_diff,
    format_activity_table,
    resolve_activity_val,
)
from codecks_cli.formatters._cards import (
    format_account_table,
    format_card_detail,
    format_cards_csv,
    format_cards_table,
    format_conversations_table,
)
from codecks_cli.formatters._core import (
    _card_section,
    mutation_response,
    output,
    pretty_print,
)
from codecks_cli.formatters._dashboards import (
    format_pm_focus_table,
    format_standup_table,
)
from codecks_cli.formatters._entities import (
    format_decks_table,
    format_milestones_table,
    format_projects_table,
    format_stats_table,
)
from codecks_cli.formatters._gdd import (
    format_gdd_table,
    format_sync_report,
)
from codecks_cli.formatters._table import (
    _CONTROL_RE,
    _sanitize_str,
    _table,
    _trunc,
)

__all__ = [
    "_CONTROL_RE",
    "_card_section",
    "_sanitize_str",
    "_table",
    "_trunc",
    "format_account_table",
    "format_activity_diff",
    "format_activity_table",
    "format_card_detail",
    "format_cards_csv",
    "format_cards_table",
    "format_conversations_table",
    "format_decks_table",
    "format_gdd_table",
    "format_milestones_table",
    "format_pm_focus_table",
    "format_projects_table",
    "format_standup_table",
    "format_stats_table",
    "format_sync_report",
    "mutation_response",
    "output",
    "pretty_print",
    "resolve_activity_val",
]
