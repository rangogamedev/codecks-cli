"""
Typed models for command payloads and PM feature scaffolding.
"""

from dataclasses import dataclass

from config import CliError


@dataclass(frozen=True)
class ObjectPayload:
    """Typed wrapper for raw JSON object payloads."""
    data: dict

    @classmethod
    def from_value(cls, value, context):
        if isinstance(value, dict):
            return cls(data=value)
        raise CliError(
            f"[ERROR] Invalid JSON in {context}: expected object, "
            f"got {type(value).__name__}."
        )


@dataclass(frozen=True)
class FeatureSpec:
    """Validated input contract for `feature` scaffolding."""
    title: str
    hero_deck: str
    code_deck: str
    design_deck: str
    art_deck: str | None
    skip_art: bool
    description: str | None
    owner: str | None
    priority: str | None
    effort: int | None
    format: str

    @classmethod
    def from_namespace(cls, ns):
        title = (ns.title or "").strip()
        if not title:
            raise CliError("[ERROR] Feature title cannot be empty.")
        if ns.skip_art and ns.art_deck:
            raise CliError("[ERROR] Use either --skip-art or --art-deck, not both.")
        if not ns.skip_art and not ns.art_deck:
            raise CliError("[ERROR] --art-deck is required unless --skip-art is set.")
        return cls(
            title=title,
            hero_deck=ns.hero_deck,
            code_deck=ns.code_deck,
            design_deck=ns.design_deck,
            art_deck=ns.art_deck,
            skip_art=ns.skip_art,
            description=ns.description,
            owner=ns.owner,
            priority=ns.priority,
            effort=ns.effort,
            format=ns.format,
        )


@dataclass(frozen=True)
class FeatureSubcard:
    lane: str
    id: str

    def to_dict(self):
        return {"lane": self.lane, "id": self.id}


@dataclass(frozen=True)
class FeatureScaffoldReport:
    hero_id: str
    hero_title: str
    subcards: list[FeatureSubcard]
    hero_deck: str
    code_deck: str
    design_deck: str
    art_deck: str | None

    def to_dict(self):
        return {
            "ok": True,
            "hero": {"id": self.hero_id, "title": self.hero_title},
            "subcards": [x.to_dict() for x in self.subcards],
            "decks": {
                "hero": self.hero_deck,
                "code": self.code_deck,
                "design": self.design_deck,
                "art": self.art_deck,
            },
        }
