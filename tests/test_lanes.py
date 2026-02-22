"""Tests for the lane registry."""

import pytest

from codecks_cli.lanes import (
    LANES,
    defaults_map,
    get_lane,
    keywords_map,
    lane_names,
    optional_lanes,
    required_lanes,
)


class TestLaneRegistry:
    def test_has_code_and_design(self):
        names = lane_names()
        assert "code" in names
        assert "design" in names

    def test_code_and_design_are_required(self):
        req = required_lanes()
        req_names = [lane.name for lane in req]
        assert "code" in req_names
        assert "design" in req_names

    def test_art_and_audio_are_optional(self):
        opt = optional_lanes()
        opt_names = [lane.name for lane in opt]
        assert "art" in opt_names
        assert "audio" in opt_names

    def test_names_are_unique(self):
        names = lane_names()
        assert len(names) == len(set(names))

    def test_all_lanes_have_keywords(self):
        for lane in LANES:
            assert len(lane.keywords) > 0, f"{lane.name} has no keywords"

    def test_all_lanes_have_tags(self):
        for lane in LANES:
            assert len(lane.tags) > 0, f"{lane.name} has no tags"

    def test_all_lanes_have_default_checklist(self):
        for lane in LANES:
            assert len(lane.default_checklist) > 0, f"{lane.name} has no defaults"

    def test_get_lane_returns_correct_lane(self):
        lane = get_lane("code")
        assert lane.name == "code"
        assert lane.display_name == "Code"
        assert lane.required is True

    def test_get_lane_raises_for_unknown(self):
        with pytest.raises(KeyError, match="Unknown lane"):
            get_lane("nonexistent")

    def test_keywords_map_matches_registry(self):
        kw = keywords_map()
        for lane in LANES:
            assert lane.name in kw
            assert kw[lane.name] == list(lane.keywords)

    def test_defaults_map_matches_registry(self):
        dm = defaults_map()
        for lane in LANES:
            assert lane.name in dm
            assert dm[lane.name] == list(lane.default_checklist)

    def test_lane_definitions_are_frozen(self):
        lane = get_lane("code")
        with pytest.raises(AttributeError):
            lane.name = "other"
