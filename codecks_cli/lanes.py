"""Lane registry — single source of truth for deck categories.

Standalone module (no project imports). Adding a new category means
appending one LaneDefinition to LANES.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LaneDefinition:
    """One deck category (e.g. code, design, art, audio)."""

    name: str
    display_name: str
    required: bool
    keywords: tuple[str, ...]
    default_checklist: tuple[str, ...]
    tags: tuple[str, ...]
    cli_help: str


LANES: tuple[LaneDefinition, ...] = (
    LaneDefinition(
        name="code",
        display_name="Code",
        required=True,
        keywords=(
            "implement",
            "build",
            "create bp_",
            "struct",
            "function",
            "test:",
            "logic",
            "system",
            "enum",
            "component",
            "manager",
            "tracking",
            "handle",
            "wire",
            "connect",
            "refactor",
            "fix",
            "debug",
            "integrate",
            "script",
            "blueprint",
            "variable",
            "class",
            "method",
        ),
        default_checklist=(
            "Implement core logic",
            "Handle edge cases",
            "Add tests/verification",
        ),
        tags=("code", "feature"),
        cli_help="Code sub-card deck",
    ),
    LaneDefinition(
        name="design",
        display_name="Design",
        required=True,
        keywords=(
            "balance",
            "tune",
            "playtest",
            "define",
            "pacing",
            "feel",
            "scaling",
            "progression",
            "economy",
            "curve",
            "difficulty",
            "feedback",
            "flow",
            "reward",
            "threshold",
        ),
        default_checklist=(
            "Define target player feel",
            "Tune balance/economy parameters",
            "Run playtest and iterate",
        ),
        tags=("design", "feel", "economy", "feature"),
        cli_help="Design sub-card deck",
    ),
    LaneDefinition(
        name="art",
        display_name="Art",
        required=False,
        keywords=(
            "sprite",
            "animation",
            "visual",
            "portrait",
            "ui layout",
            "effect",
            "icon",
            "color",
            "asset",
            "texture",
            "particle",
            "vfx",
        ),
        default_checklist=(
            "Create required assets/content",
            "Integrate assets in game flow",
            "Visual quality pass",
        ),
        tags=("art", "feature"),
        cli_help="Art sub-card deck",
    ),
    LaneDefinition(
        name="audio",
        display_name="Audio",
        required=False,
        keywords=(
            "sfx",
            "sound",
            "music",
            "audio",
            "voice",
            "dialogue",
            "ambient",
            "foley",
            "mix",
            "volume",
            "bgm",
            "jingle",
        ),
        default_checklist=(
            "Create required audio assets",
            "Integrate audio in game flow",
            "Audio quality/mix pass",
        ),
        tags=("audio", "feature"),
        cli_help="Audio sub-card deck",
    ),
)


def get_lane(name: str) -> LaneDefinition:
    """Return a lane by name. Raises KeyError if not found."""
    for lane in LANES:
        if lane.name == name:
            return lane
    raise KeyError(f"Unknown lane: {name!r}")


def required_lanes() -> tuple[LaneDefinition, ...]:
    """Return only required lanes."""
    return tuple(lane for lane in LANES if lane.required)


def optional_lanes() -> tuple[LaneDefinition, ...]:
    """Return only optional lanes."""
    return tuple(lane for lane in LANES if not lane.required)


def lane_names() -> tuple[str, ...]:
    """Return all lane names in registration order."""
    return tuple(lane.name for lane in LANES)


def keywords_map() -> dict[str, list[str]]:
    """Return {lane_name: [keywords...]} for classification."""
    return {lane.name: list(lane.keywords) for lane in LANES}


def defaults_map() -> dict[str, list[str]]:
    """Return {lane_name: [default_checklist...]} for empty-lane filling."""
    return {lane.name: list(lane.default_checklist) for lane in LANES}
