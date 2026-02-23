"""Tag registry — single source of truth for project tag definitions.

Standalone module (no project imports). Adding a new tag means
appending one TagDefinition to TAGS and optionally updating LANE_TAGS.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TagDefinition:
    """One project-level tag (maps to a Codecks masterTag)."""

    name: str
    display_name: str
    category: str  # "system" or "discipline"
    description: str


TAGS: tuple[TagDefinition, ...] = (
    # System tags — structural markers used by feature scaffolding
    TagDefinition("hero", "Hero", "system", "Feature hero card marker"),
    TagDefinition("feature", "Feature", "system", "Feature scope marker"),
    # Discipline tags — work-type identifiers applied to lane sub-cards
    TagDefinition("code", "Code", "discipline", "Code implementation work"),
    TagDefinition("design", "Design", "discipline", "Game design work"),
    TagDefinition("feel", "Feel", "discipline", "Game feel and player experience"),
    TagDefinition("economy", "Economy", "discipline", "Economy and balance design"),
    TagDefinition("art", "Art", "discipline", "Visual art and assets"),
    TagDefinition("audio", "Audio", "discipline", "Sound and music"),
)

# -- Pre-built tag sets for common contexts --

HERO_TAGS: tuple[str, ...] = ("hero", "feature")

LANE_TAGS: dict[str, tuple[str, ...]] = {
    "code": ("code", "feature"),
    "design": ("design", "feel", "economy", "feature"),
    "art": ("art", "feature"),
    "audio": ("audio", "feature"),
}


# -- Helpers --


def get_tag(name: str) -> TagDefinition:
    """Return a tag by name. Raises KeyError if not found."""
    for tag in TAGS:
        if tag.name == name:
            return tag
    raise KeyError(f"Unknown tag: {name!r}")


def tags_by_category(category: str) -> tuple[TagDefinition, ...]:
    """Return all tags in the given category."""
    return tuple(tag for tag in TAGS if tag.category == category)


def tag_names() -> tuple[str, ...]:
    """Return all tag names in registration order."""
    return tuple(tag.name for tag in TAGS)


def lane_tag_names(lane_name: str) -> tuple[str, ...]:
    """Return tag names for a given lane. Raises KeyError if lane unknown."""
    try:
        return LANE_TAGS[lane_name]
    except KeyError:
        raise KeyError(f"No tags defined for lane: {lane_name!r}") from None
