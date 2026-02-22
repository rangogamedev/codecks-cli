"""Tests for typed models used by command orchestration."""

import argparse

import pytest

from codecks_cli.exceptions import CliError
from codecks_cli.models import (
    FeatureScaffoldReport,
    FeatureSpec,
    FeatureSubcard,
    ObjectPayload,
    SplitFeaturesSpec,
)


class TestObjectPayload:
    def test_accepts_object(self):
        payload = ObjectPayload.from_value({"a": 1}, "query")
        assert payload.data == {"a": 1}

    def test_rejects_non_object(self):
        with pytest.raises(CliError) as exc_info:
            ObjectPayload.from_value([1, 2, 3], "query")
        assert "expected object" in str(exc_info.value)


class TestFeatureSpec:
    def _ns(self, **kwargs):
        base = {
            "title": "Combat",
            "hero_deck": "Features",
            "code_deck": "Code",
            "design_deck": "Design",
            "art_deck": "Art",
            "skip_art": False,
            "audio_deck": None,
            "skip_audio": False,
            "description": None,
            "owner": None,
            "priority": None,
            "effort": None,
            "format": "json",
            "allow_duplicate": False,
        }
        base.update(kwargs)
        return argparse.Namespace(**base)

    def test_valid_spec(self):
        spec = FeatureSpec.from_namespace(self._ns())
        assert spec.title == "Combat"
        assert spec.art_deck == "Art"

    def test_rejects_empty_title(self):
        with pytest.raises(CliError):
            FeatureSpec.from_namespace(self._ns(title="  "))

    def test_rejects_skip_art_with_art_deck(self):
        with pytest.raises(CliError):
            FeatureSpec.from_namespace(self._ns(skip_art=True, art_deck="Art"))

    def test_requires_art_deck_unless_skip(self):
        spec = FeatureSpec.from_namespace(self._ns(art_deck=None, skip_art=False))
        assert spec.skip_art is True
        assert spec.auto_skip_art is True
        assert spec.art_deck is None

    def test_allow_duplicate_passthrough(self):
        spec = FeatureSpec.from_namespace(self._ns(allow_duplicate=True))
        assert spec.allow_duplicate is True

    def test_audio_deck_passthrough(self):
        spec = FeatureSpec.from_namespace(self._ns(audio_deck="Audio"))
        assert spec.audio_deck == "Audio"
        assert spec.skip_audio is False
        assert spec.auto_skip_audio is False

    def test_auto_skips_audio_when_no_deck(self):
        spec = FeatureSpec.from_namespace(self._ns(audio_deck=None, skip_audio=False))
        assert spec.skip_audio is True
        assert spec.auto_skip_audio is True
        assert spec.audio_deck is None

    def test_rejects_skip_audio_with_audio_deck(self):
        with pytest.raises(CliError):
            FeatureSpec.from_namespace(self._ns(skip_audio=True, audio_deck="Audio"))

    def test_from_kwargs_audio(self):
        spec = FeatureSpec.from_kwargs(
            "Combat",
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            audio_deck="Audio",
        )
        assert spec.audio_deck == "Audio"
        assert spec.skip_audio is False

    def test_from_kwargs_rejects_skip_audio_with_audio_deck(self):
        with pytest.raises(CliError):
            FeatureSpec.from_kwargs(
                "Combat",
                hero_deck="Features",
                code_deck="Code",
                design_deck="Design",
                skip_audio=True,
                audio_deck="Audio",
            )


class TestFeatureScaffoldReport:
    def test_to_dict(self):
        rep = FeatureScaffoldReport(
            hero_id="h1",
            hero_title="Feature: Combat",
            subcards=[FeatureSubcard(lane="code", id="c1")],
            hero_deck="Features",
            lane_decks={"code": "Code", "design": "Design", "art": None, "audio": None},
        )
        data = rep.to_dict()
        assert data["ok"] is True
        assert data["hero"]["id"] == "h1"
        assert data["subcards"][0]["lane"] == "code"
        assert data["decks"]["audio"] is None

    def test_to_dict_with_notes(self):
        rep = FeatureScaffoldReport(
            hero_id="h1",
            hero_title="Feature: Combat",
            subcards=[],
            hero_deck="Features",
            lane_decks={"code": "Code", "design": "Design", "art": None, "audio": None},
            notes=["Art lane auto-skipped"],
        )
        data = rep.to_dict()
        assert data["notes"] == ["Art lane auto-skipped"]

    def test_to_dict_with_audio_deck(self):
        rep = FeatureScaffoldReport(
            hero_id="h1",
            hero_title="Feature: Combat",
            subcards=[FeatureSubcard(lane="audio", id="a1")],
            hero_deck="Features",
            lane_decks={"code": "Code", "design": "Design", "art": None, "audio": "Audio"},
        )
        data = rep.to_dict()
        assert data["decks"]["audio"] == "Audio"

    def test_backward_compat_properties(self):
        rep = FeatureScaffoldReport(
            hero_id="h1",
            hero_title="Feature: Combat",
            subcards=[],
            hero_deck="Features",
            lane_decks={"code": "Code", "design": "Design", "art": "Art", "audio": None},
        )
        assert rep.code_deck == "Code"
        assert rep.design_deck == "Design"
        assert rep.art_deck == "Art"
        assert rep.audio_deck is None


class TestSplitFeaturesSpec:
    def _ns(self, **kwargs):
        base = {
            "deck": "Features",
            "code_deck": "Code",
            "design_deck": "Design",
            "art_deck": None,
            "skip_art": False,
            "audio_deck": None,
            "skip_audio": False,
            "priority": None,
            "dry_run": False,
        }
        base.update(kwargs)
        return argparse.Namespace(**base)

    def test_audio_deck_passthrough(self):
        spec = SplitFeaturesSpec.from_namespace(self._ns(audio_deck="Audio"))
        assert spec.audio_deck == "Audio"
        assert spec.skip_audio is False

    def test_auto_skips_audio_when_no_deck(self):
        spec = SplitFeaturesSpec.from_namespace(self._ns())
        assert spec.skip_audio is True
        assert spec.audio_deck is None

    def test_rejects_skip_audio_with_audio_deck(self):
        with pytest.raises(CliError):
            SplitFeaturesSpec.from_namespace(self._ns(skip_audio=True, audio_deck="Audio"))

    def test_from_kwargs_audio(self):
        spec = SplitFeaturesSpec.from_kwargs(
            deck="Features",
            code_deck="Code",
            design_deck="Design",
            audio_deck="Audio",
        )
        assert spec.audio_deck == "Audio"
        assert spec.skip_audio is False

    def test_from_kwargs_rejects_skip_audio_with_audio_deck(self):
        with pytest.raises(CliError):
            SplitFeaturesSpec.from_kwargs(
                deck="Features",
                code_deck="Code",
                design_deck="Design",
                skip_audio=True,
                audio_deck="Audio",
            )
