"""Tests for the tag registry."""

import pytest

from codecks_cli.tags import (
    HERO_TAGS,
    LANE_TAGS,
    TAGS,
    get_tag,
    lane_tag_names,
    tag_names,
    tags_by_category,
)


class TestTagRegistry:
    def test_has_system_tags(self):
        names = tag_names()
        assert "hero" in names
        assert "feature" in names

    def test_has_discipline_tags(self):
        names = tag_names()
        for name in ("code", "design", "feel", "economy", "art", "audio"):
            assert name in names, f"Missing discipline tag: {name}"

    def test_names_are_unique(self):
        names = tag_names()
        assert len(names) == len(set(names))

    def test_all_tags_have_required_fields(self):
        for tag in TAGS:
            assert tag.name, "Tag missing name"
            assert tag.display_name, f"{tag.name} missing display_name"
            assert tag.category in ("system", "discipline"), (
                f"{tag.name} has invalid category: {tag.category}"
            )
            assert tag.description, f"{tag.name} missing description"

    def test_tag_definitions_are_frozen(self):
        tag = get_tag("hero")
        with pytest.raises(AttributeError):
            tag.name = "other"

    def test_get_tag_returns_correct_tag(self):
        tag = get_tag("code")
        assert tag.name == "code"
        assert tag.display_name == "Code"
        assert tag.category == "discipline"

    def test_get_tag_raises_for_unknown(self):
        with pytest.raises(KeyError, match="Unknown tag"):
            get_tag("nonexistent")

    def test_tags_by_category_system(self):
        system = tags_by_category("system")
        names = [t.name for t in system]
        assert "hero" in names
        assert "feature" in names
        assert "code" not in names

    def test_tags_by_category_discipline(self):
        disc = tags_by_category("discipline")
        names = [t.name for t in disc]
        assert "code" in names
        assert "design" in names
        assert "hero" not in names

    def test_tags_by_category_empty(self):
        result = tags_by_category("nonexistent")
        assert result == ()


class TestHeroTags:
    def test_hero_tags_contains_hero_and_feature(self):
        assert "hero" in HERO_TAGS
        assert "feature" in HERO_TAGS

    def test_hero_tags_all_exist_in_registry(self):
        names = tag_names()
        for tag_name in HERO_TAGS:
            assert tag_name in names, f"HERO_TAGS references unknown tag: {tag_name}"


class TestLaneTags:
    def test_all_lanes_have_entries(self):
        for lane_name in ("code", "design", "art", "audio"):
            assert lane_name in LANE_TAGS, f"Missing LANE_TAGS entry: {lane_name}"

    def test_all_lane_tags_exist_in_registry(self):
        names = tag_names()
        for lane_name, lane_tags in LANE_TAGS.items():
            for tag_name in lane_tags:
                assert tag_name in names, (
                    f"LANE_TAGS[{lane_name!r}] references unknown tag: {tag_name}"
                )

    def test_all_lanes_include_feature_tag(self):
        for lane_name, lane_tags in LANE_TAGS.items():
            assert "feature" in lane_tags, f"LANE_TAGS[{lane_name!r}] missing 'feature' tag"

    def test_lane_tag_names_helper(self):
        result = lane_tag_names("code")
        assert result == ("code", "feature")

    def test_lane_tag_names_raises_for_unknown(self):
        with pytest.raises(KeyError, match="No tags defined for lane"):
            lane_tag_names("nonexistent")

    def test_design_lane_has_discipline_tags(self):
        result = lane_tag_names("design")
        assert "design" in result
        assert "feel" in result
        assert "economy" in result
        assert "feature" in result
