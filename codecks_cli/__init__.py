"""codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects."""

from codecks_cli.client import CodecksClient
from codecks_cli.config import VERSION
from codecks_cli.exceptions import CliError, SetupError
from codecks_cli.types import (
    CardDetail,
    CardListResult,
    CardRow,
    CardStats,
    CreateCardResult,
    DeckRow,
    HandResult,
    MilestoneRow,
    MutationResult,
    PmFocusResult,
    ProjectRow,
    StandupResult,
    UpdateCardsResult,
)

__all__ = [
    "VERSION",
    "CodecksClient",
    "CliError",
    "SetupError",
    "CardDetail",
    "CardListResult",
    "CardRow",
    "CardStats",
    "CreateCardResult",
    "DeckRow",
    "HandResult",
    "MilestoneRow",
    "MutationResult",
    "PmFocusResult",
    "ProjectRow",
    "StandupResult",
    "UpdateCardsResult",
]
