"""
Typed models for command payloads and PM feature scaffolding.
"""

from dataclasses import dataclass, field

from codecks_cli.exceptions import CliError
from codecks_cli.lanes import LANES, lane_names


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
    lane_decks: dict[str, str | None]
    lane_skips: dict[str, bool]
    lane_auto_skips: dict[str, bool]
    description: str | None
    owner: str | None
    priority: str | None
    effort: int | None
    format: str
    allow_duplicate: bool

    # --- Backward-compat properties ---

    @property
    def code_deck(self) -> str:
        return self.lane_decks["code"]  # type: ignore[return-value]

    @property
    def design_deck(self) -> str:
        return self.lane_decks["design"]  # type: ignore[return-value]

    @property
    def art_deck(self) -> str | None:
        return self.lane_decks.get("art")

    @property
    def skip_art(self) -> bool:
        return self.lane_skips.get("art", True)

    @property
    def auto_skip_art(self) -> bool:
        return self.lane_auto_skips.get("art", True)

    @property
    def audio_deck(self) -> str | None:
        return self.lane_decks.get("audio")

    @property
    def skip_audio(self) -> bool:
        return self.lane_skips.get("audio", True)

    @property
    def auto_skip_audio(self) -> bool:
        return self.lane_auto_skips.get("audio", True)

    @classmethod
    def _resolve_lane_args(cls, lane_args):
        """Resolve skip/auto-skip logic for each optional lane.

        Args:
            lane_args: dict of {lane_name: (deck_value, skip_flag)}

        Returns:
            (lane_decks, lane_skips, lane_auto_skips)
        """
        lane_decks: dict[str, str | None] = {}
        lane_skips: dict[str, bool] = {}
        lane_auto_skips: dict[str, bool] = {}

        for lane_def in LANES:
            name = lane_def.name
            deck_val, skip_flag = lane_args.get(name, (None, False))

            if lane_def.required:
                # Required lanes: deck must be provided, no skip logic
                lane_decks[name] = deck_val
                lane_skips[name] = False
                lane_auto_skips[name] = False
            else:
                # Optional lanes: skip XOR deck validation
                if skip_flag and deck_val:
                    raise CliError(f"[ERROR] Use either --skip-{name} or --{name}-deck, not both.")
                auto_skip = bool((not skip_flag) and (not deck_val))
                skip = bool(skip_flag or auto_skip)
                lane_decks[name] = None if skip else deck_val
                lane_skips[name] = skip
                lane_auto_skips[name] = auto_skip

        return lane_decks, lane_skips, lane_auto_skips

    @classmethod
    def from_namespace(cls, ns):
        title = (ns.title or "").strip()
        if not title:
            raise CliError("[ERROR] Feature title cannot be empty.")

        lane_args: dict[str, tuple] = {}
        for lane_def in LANES:
            name = lane_def.name
            if lane_def.required:
                lane_args[name] = (getattr(ns, f"{name}_deck"), False)
            else:
                lane_args[name] = (
                    getattr(ns, f"{name}_deck", None),
                    getattr(ns, f"skip_{name}", False),
                )

        lane_decks, lane_skips, lane_auto_skips = cls._resolve_lane_args(lane_args)

        return cls(
            title=title,
            hero_deck=ns.hero_deck,
            lane_decks=lane_decks,
            lane_skips=lane_skips,
            lane_auto_skips=lane_auto_skips,
            description=ns.description,
            owner=ns.owner,
            priority=ns.priority,
            effort=ns.effort,
            format=ns.format,
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
        audio_deck=None,
        skip_audio=False,
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

        # Build lane_args from explicit kwargs
        # Map known kwargs to lane names
        deck_kwargs = {
            "code": code_deck,
            "design": design_deck,
            "art": art_deck,
            "audio": audio_deck,
        }
        skip_kwargs = {"art": skip_art, "audio": skip_audio}

        lane_args: dict[str, tuple] = {}
        for lane_def in LANES:
            name = lane_def.name
            deck_val = deck_kwargs.get(name)
            skip_val = skip_kwargs.get(name, False) if not lane_def.required else False
            lane_args[name] = (deck_val, skip_val)

        lane_decks, lane_skips, lane_auto_skips = cls._resolve_lane_args(lane_args)

        return cls(
            title=title,
            hero_deck=hero_deck,
            lane_decks=lane_decks,
            lane_skips=lane_skips,
            lane_auto_skips=lane_auto_skips,
            description=description,
            owner=owner,
            priority=priority,
            effort=effort,
            format=format,
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
    lane_decks: dict[str, str | None] = field(default_factory=dict)
    notes: list[str] | None = None

    # --- Backward-compat properties ---

    @property
    def code_deck(self) -> str:
        return self.lane_decks.get("code", "")  # type: ignore[return-value]

    @property
    def design_deck(self) -> str:
        return self.lane_decks.get("design", "")  # type: ignore[return-value]

    @property
    def art_deck(self) -> str | None:
        return self.lane_decks.get("art")

    @property
    def audio_deck(self) -> str | None:
        return self.lane_decks.get("audio")

    def to_dict(self):
        decks: dict[str, str | None] = {"hero": self.hero_deck}
        for name in lane_names():
            decks[name] = self.lane_decks.get(name)
        out = {
            "ok": True,
            "hero": {"id": self.hero_id, "title": self.hero_title},
            "subcards": [x.to_dict() for x in self.subcards],
            "decks": decks,
        }
        if self.notes:
            out["notes"] = self.notes
        return out


@dataclass(frozen=True)
class SplitFeaturesSpec:
    """Validated input contract for `split-features` batch decomposition."""

    deck: str
    lane_decks: dict[str, str | None]
    lane_skips: dict[str, bool]
    priority: str | None
    dry_run: bool

    # --- Backward-compat properties ---

    @property
    def code_deck(self) -> str:
        return self.lane_decks["code"]  # type: ignore[return-value]

    @property
    def design_deck(self) -> str:
        return self.lane_decks["design"]  # type: ignore[return-value]

    @property
    def art_deck(self) -> str | None:
        return self.lane_decks.get("art")

    @property
    def skip_art(self) -> bool:
        return self.lane_skips.get("art", True)

    @property
    def audio_deck(self) -> str | None:
        return self.lane_decks.get("audio")

    @property
    def skip_audio(self) -> bool:
        return self.lane_skips.get("audio", True)

    @classmethod
    def _resolve_lane_args(cls, lane_args):
        """Resolve skip logic for each lane.

        Args:
            lane_args: dict of {lane_name: (deck_value, skip_flag)}

        Returns:
            (lane_decks, lane_skips)
        """
        lane_decks: dict[str, str | None] = {}
        lane_skips: dict[str, bool] = {}

        for lane_def in LANES:
            name = lane_def.name
            deck_val, skip_flag = lane_args.get(name, (None, False))

            if lane_def.required:
                lane_decks[name] = deck_val
                lane_skips[name] = False
            else:
                if skip_flag and deck_val:
                    raise CliError(f"[ERROR] Use either --skip-{name} or --{name}-deck, not both.")
                skip = bool(skip_flag or (not deck_val))
                lane_decks[name] = None if skip else deck_val
                lane_skips[name] = skip

        return lane_decks, lane_skips

    @classmethod
    def from_namespace(cls, ns):
        lane_args: dict[str, tuple] = {}
        for lane_def in LANES:
            name = lane_def.name
            if lane_def.required:
                lane_args[name] = (getattr(ns, f"{name}_deck"), False)
            else:
                lane_args[name] = (
                    getattr(ns, f"{name}_deck", None),
                    getattr(ns, f"skip_{name}", False),
                )

        lane_decks, lane_skips = cls._resolve_lane_args(lane_args)

        return cls(
            deck=ns.deck,
            lane_decks=lane_decks,
            lane_skips=lane_skips,
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
        audio_deck=None,
        skip_audio=False,
        priority=None,
        dry_run=False,
    ):
        """Create from keyword arguments (programmatic API / MCP)."""
        deck_kwargs = {
            "code": code_deck,
            "design": design_deck,
            "art": art_deck,
            "audio": audio_deck,
        }
        skip_kwargs = {"art": skip_art, "audio": skip_audio}

        lane_args: dict[str, tuple] = {}
        for lane_def in LANES:
            name = lane_def.name
            deck_val = deck_kwargs.get(name)
            skip_val = skip_kwargs.get(name, False) if not lane_def.required else False
            lane_args[name] = (deck_val, skip_val)

        lane_decks, lane_skips = cls._resolve_lane_args(lane_args)

        return cls(
            deck=deck,
            lane_decks=lane_decks,
            lane_skips=lane_skips,
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
