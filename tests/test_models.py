"""Tests for typed models used by command orchestration."""

import argparse

import pytest

from codecks_cli.exceptions import CliError
from codecks_cli.models import FeatureScaffoldReport, FeatureSpec, FeatureSubcard, ObjectPayload


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


class TestFeatureScaffoldReport:
    def test_to_dict(self):
        rep = FeatureScaffoldReport(
            hero_id="h1",
            hero_title="Feature: Combat",
            subcards=[FeatureSubcard(lane="code", id="c1")],
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
        )
        data = rep.to_dict()
        assert data["ok"] is True
        assert data["hero"]["id"] == "h1"
        assert data["subcards"][0]["lane"] == "code"

    def test_to_dict_with_notes(self):
        rep = FeatureScaffoldReport(
            hero_id="h1",
            hero_title="Feature: Combat",
            subcards=[],
            hero_deck="Features",
            code_deck="Code",
            design_deck="Design",
            art_deck=None,
            notes=["Art lane auto-skipped"],
        )
        data = rep.to_dict()
        assert data["notes"] == ["Art lane auto-skipped"]
