"""Lane registry — single source of truth for deck categories.

Imports only tags.py and config.py (standalone data modules). Adding a new
category means appending one LaneDefinition to LANES and updating
LANE_TAGS in tags.py.

Lane default checklists can be overridden via a ``.codecks_lanes.json`` file
in the project root. See ``_load_lane_config()`` for details.
"""

import json
import os
from dataclasses import dataclass

from codecks_cli.config import _PROJECT_ROOT
from codecks_cli.tags import LANE_TAGS


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
        tags=LANE_TAGS["code"],
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
        tags=LANE_TAGS["design"],
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
        tags=LANE_TAGS["art"],
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
        tags=LANE_TAGS["audio"],
        cli_help="Audio sub-card deck",
    ),
)


_LANE_CONFIG_FILE = ".codecks_lanes.json"
_LANE_CONFIG_PATH = os.path.join(_PROJECT_ROOT, _LANE_CONFIG_FILE)


def _load_lane_config() -> dict[str, list[str]]:
    """Load lane checklist overrides from ``.codecks_lanes.json``.

    Expected format::

        {
            "code": ["Step 1", "Step 2"],
            "design": ["Design step 1"]
        }

    Returns:
        Mapping of lane name → checklist items.  Empty dict if the
        config file is missing or malformed.
    """
    try:
        with open(_LANE_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    overrides: dict[str, list[str]] = {}
    for key, value in data.items():
        if (
            isinstance(key, str)
            and isinstance(value, list)
            and all(isinstance(v, str) for v in value)
        ):
            overrides[key] = value
    return overrides


def _apply_lane_overrides(
    lanes: tuple[LaneDefinition, ...],
    overrides: dict[str, list[str]],
) -> tuple[LaneDefinition, ...]:
    """Return a new LANES tuple with default_checklist overridden where configured."""
    if not overrides:
        return lanes
    result: list[LaneDefinition] = []
    for lane in lanes:
        if lane.name in overrides:
            lane = LaneDefinition(
                name=lane.name,
                display_name=lane.display_name,
                required=lane.required,
                keywords=lane.keywords,
                default_checklist=tuple(overrides[lane.name]),
                tags=lane.tags,
                cli_help=lane.cli_help,
            )
        result.append(lane)
    return tuple(result)


# Apply config file overrides (no-op if file is missing)
LANES = _apply_lane_overrides(LANES, _load_lane_config())


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
