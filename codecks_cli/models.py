"""
Typed models for command payloads and PM feature scaffolding.
"""

from dataclasses import dataclass

from codecks_cli.exceptions import CliError


@dataclass(frozen=True)
class ObjectPayload:
    """Typed wrapper for raw JSON object payloads."""

    data: dict

    @classmethod
    def from_value(cls, value, context):
        if isinstance(value, dict):
            return cls(data=value)
        raise CliError(
            f"[ERROR] Invalid JSON in {context}: expected object, got {type(value).__name__}."
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
    auto_skip_art: bool
    allow_duplicate: bool

    @classmethod
    def from_namespace(cls, ns):
        title = (ns.title or "").strip()
        if not title:
            raise CliError("[ERROR] Feature title cannot be empty.")
        if ns.skip_art and ns.art_deck:
            raise CliError("[ERROR] Use either --skip-art or --art-deck, not both.")
        auto_skip_art = bool((not ns.skip_art) and (not ns.art_deck))
        skip_art = bool(ns.skip_art or auto_skip_art)
        return cls(
            title=title,
            hero_deck=ns.hero_deck,
            code_deck=ns.code_deck,
            design_deck=ns.design_deck,
            art_deck=None if skip_art else ns.art_deck,
            skip_art=skip_art,
            description=ns.description,
            owner=ns.owner,
            priority=ns.priority,
            effort=ns.effort,
            format=ns.format,
            auto_skip_art=auto_skip_art,
            allow_duplicate=bool(getattr(ns, "allow_duplicate", False)),
        )

    @classmethod
    def from_kwargs(
        cls,
        title,
        *,
        hero_deck,
        code_deck,
        design_deck,
        art_deck=None,
        skip_art=False,
        description=None,
        owner=None,
        priority=None,
        effort=None,
        format="json",
        allow_duplicate=False,
    ):
        """Create a FeatureSpec from keyword arguments (programmatic API)."""
        title = (title or "").strip()
        if not title:
            raise CliError("[ERROR] Feature title cannot be empty.")
        if skip_art and art_deck:
            raise CliError("[ERROR] Use either --skip-art or --art-deck, not both.")
        auto_skip_art = bool((not skip_art) and (not art_deck))
        skip_art = bool(skip_art or auto_skip_art)
        return cls(
            title=title,
            hero_deck=hero_deck,
            code_deck=code_deck,
            design_deck=design_deck,
            art_deck=None if skip_art else art_deck,
            skip_art=skip_art,
            description=description,
            owner=owner,
            priority=priority,
            effort=effort,
            format=format,
            auto_skip_art=auto_skip_art,
            allow_duplicate=allow_duplicate,
        )


@dataclass(frozen=True)
class FeatureSubcard:
    lane: str
    id: str
    title: str | None = None

    def to_dict(self):
        out = {"lane": self.lane, "id": self.id}
        if self.title is not None:
            out["title"] = self.title
        return out


@dataclass(frozen=True)
class FeatureScaffoldReport:
    hero_id: str
    hero_title: str
    subcards: list[FeatureSubcard]
    hero_deck: str
    code_deck: str
    design_deck: str
    art_deck: str | None
    notes: list[str] | None = None

    def to_dict(self):
        out = {
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
        if self.notes:
            out["notes"] = self.notes
        return out


@dataclass(frozen=True)
class SplitFeaturesSpec:
    """Validated input contract for `split-features` batch decomposition."""

    deck: str
    code_deck: str
    design_deck: str
    art_deck: str | None
    skip_art: bool
    priority: str | None
    dry_run: bool

    @classmethod
    def from_namespace(cls, ns):
        if ns.skip_art and ns.art_deck:
            raise CliError("[ERROR] Use either --skip-art or --art-deck, not both.")
        skip_art = bool(ns.skip_art or (not ns.art_deck))
        return cls(
            deck=ns.deck,
            code_deck=ns.code_deck,
            design_deck=ns.design_deck,
            art_deck=None if skip_art else ns.art_deck,
            skip_art=skip_art,
            priority=ns.priority,
            dry_run=bool(ns.dry_run),
        )

    @classmethod
    def from_kwargs(
        cls,
        *,
        deck,
        code_deck,
        design_deck,
        art_deck=None,
        skip_art=False,
        priority=None,
        dry_run=False,
    ):
        """Create from keyword arguments (programmatic API / MCP)."""
        if skip_art and art_deck:
            raise CliError("[ERROR] Use either --skip-art or --art-deck, not both.")
        skip_art = bool(skip_art or (not art_deck))
        return cls(
            deck=deck,
            code_deck=code_deck,
            design_deck=design_deck,
            art_deck=None if skip_art else art_deck,
            skip_art=skip_art,
            priority=priority,
            dry_run=bool(dry_run),
        )


@dataclass(frozen=True)
class SplitFeatureDetail:
    """One processed feature in a split-features batch."""

    feature_id: str
    feature_title: str
    subcards: list[FeatureSubcard]

    def to_dict(self):
        return {
            "feature_id": self.feature_id,
            "feature_title": self.feature_title,
            "subcards": [s.to_dict() for s in self.subcards],
        }


@dataclass(frozen=True)
class SplitFeaturesReport:
    """Full report from a split-features batch operation."""

    features_processed: int
    features_skipped: int
    subcards_created: int
    details: list[SplitFeatureDetail]
    skipped: list[dict]
    notes: list[str] | None = None

    def to_dict(self):
        out = {
            "ok": True,
            "features_processed": self.features_processed,
            "features_skipped": self.features_skipped,
            "subcards_created": self.subcards_created,
            "details": [d.to_dict() for d in self.details],
            "skipped": self.skipped,
        }
        if self.notes:
            out["notes"] = self.notes
        return out
