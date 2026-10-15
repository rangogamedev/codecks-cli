"""Resolve visible Codecks card references to API UUIDs."""

import json
import re
from uuid import UUID

from codecks_cli.api import query
from codecks_cli.exceptions import CliError

# Codecks' pronounceSafeSeq, linked from the official accountSeq documentation:
# https://gist.github.com/danielberndt/19857421171dbb07a3681f0ea6634049
_ALPHABET = "123456789acefghijkoqrsuvwxyz"
_OFFSET = 28 * 29 - 1
_MAX_SEQUENCE = 2**31 - 1


def _sequence(reference: str) -> int | None:
    """Parse #decimal or $pronounceSafeSeq; full UUIDs return None."""
    if reference.startswith("#") and re.fullmatch(r"#[0-9]+", reference):
        if len(reference) > 11:
            raise CliError("[ERROR] Card number exceeds int32.", error_code="INVALID_INPUT")
        number = int(reference[1:])
    elif reference.startswith("$") and 1 < len(reference) <= 9:
        code = reference[1:].lower()
        if any(char not in _ALPHABET for char in code):
            raise CliError("[ERROR] Invalid Codecks short code.", error_code="INVALID_INPUT")
        number = _ALPHABET.index(code[0])
        for char in code[1:]:
            number = (number + 1) * len(_ALPHABET) + _ALPHABET.index(char)
        number -= _OFFSET
    else:
        try:
            if len(reference) == 36 and str(UUID(reference)) == reference.lower():
                return None
        except ValueError:
            pass
        raise CliError(
            "[ERROR] Use a full UUID, #card-number, or $Codecks-reference.",
            error_code="INVALID_INPUT",
        )
    if not 1 <= number <= _MAX_SEQUENCE:
        raise CliError("[ERROR] Card number must be a positive int32.", error_code="INVALID_INPUT")
    return number


def _short_code(number: int) -> str:
    """Encode accountSeq using Codecks' offset and implicit-zero alphabet."""
    value = number + _OFFSET + 1
    chars = []
    while value:
        value, remainder = divmod(value - 1, len(_ALPHABET))
        chars.append(_ALPHABET[remainder])
    return "$" + "".join(reversed(chars))


def resolve_card_ids(references: list[str]) -> dict:
    """Resolve 1-100 references in one live query, including archived/trashed cards.

    No prefix or title matching. Missing/inaccessible references fail the whole
    request before a caller can act on a partially resolved batch.
    """
    if not isinstance(references, list) or not 1 <= len(references) <= 100:
        raise CliError("[ERROR] Provide 1-100 card references.", error_code="INVALID_INPUT")
    parsed = []
    for reference in references:
        if not isinstance(reference, str):
            raise CliError("[ERROR] Card references must be strings.", error_code="INVALID_INPUT")
        reference = reference.strip()
        parsed.append((reference, _sequence(reference)))
    numbers = sorted({number for _, number in parsed if number is not None})
    uuids = sorted({ref.lower() for ref, number in parsed if number is None})
    filters = []
    if numbers:
        filters.append({"accountSeq": {"op": "in", "value": numbers}})
    if uuids:
        filters.append({"cardId": {"op": "in", "value": uuids}})
    condition = filters[0] if len(filters) == 1 else {"$or": filters}
    result = query(
        {
            "_root": [
                {
                    "account": [
                        {
                            f"cards({json.dumps(condition)})": [
                                "cardId",
                                "accountSeq",
                                "title",
                                "visibility",
                            ]
                        }
                    ]
                }
            ]
        }
    )
    by_number: dict[int, list[tuple[str, dict]]] = {}
    by_id = {}
    for card_id, card in result.get("card", {}).items():
        by_id[card_id.lower()] = (card_id, card)
        number = card.get("accountSeq", card.get("account_seq"))
        if isinstance(number, int):
            by_number.setdefault(number, []).append((card_id, card))
    resolved = []
    for reference, number in parsed:
        matches = by_number.get(number, []) if number is not None else []
        if number is None and reference.lower() in by_id:
            matches = [by_id[reference.lower()]]
        if len(matches) != 1:
            raise CliError(
                f"[ERROR] Card reference '{reference}' is missing, inaccessible, or ambiguous.",
                error_code="INVALID_INPUT",
            )
        card_id, card = matches[0]
        sequence = card.get("accountSeq", card.get("account_seq"))
        if type(sequence) is not int or not 1 <= sequence <= _MAX_SEQUENCE:
            raise CliError(
                "[ERROR] Card response has an invalid accountSeq.", error_code="INVALID_QUERY"
            )
        resolved.append(
            {
                "reference": reference,
                "id": card_id,
                "account_seq": sequence,
                "short_code": _short_code(sequence),
                "title": card.get("title", ""),
                "visibility": card.get("visibility", "default"),
            }
        )
    return {"cards": resolved}
