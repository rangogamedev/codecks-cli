"""codecks-cli — CLI tool for managing Codecks.io cards, decks, and projects."""

from codecks_cli.client import CodecksClient
from codecks_cli.config import VERSION, CliError, SetupError

__all__ = ["VERSION", "CodecksClient", "CliError", "SetupError"]
