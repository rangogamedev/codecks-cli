"""Feature scaffolding — Hero card creation and batch splitting.

Module map: .claude/maps/scaffolding.md (read before editing)

Extracted from client.py to keep it focused on the 25 core API methods.
This module has zero overlap with other CodecksClient methods.

Public functions receive a CodecksClient instance where needed (split_features)
to avoid circular imports. scaffold_feature uses cards-layer functions directly.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from codecks_cli.cards import (
    archive_card,
    create_card,
    list_cards,
    load_users,
    resolve_deck_id,
    update_card,
)
from codecks_cli.exceptions import CliError, SetupError
from codecks_cli.lanes import LANES, defaults_map, keywords_map
from codecks_cli.models import (
    FeatureScaffoldReport,
    FeatureSpec,
    FeatureSubcard,
    SplitFeatureDetail,
    SplitFeaturesReport,
    SplitFeaturesSpec,
)
from codecks_cli.tags import HERO_TAGS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_owner_id(owner_name: str) -> str:
    """Resolve owner display name to user ID."""
    user_map = load_users()
    for uid, name in user_map.items():
        if name.lower() == owner_name.lower():
            return str(uid)
    available = list(user_map.values())
    hint = f" Available: {', '.join(available)}" if available else ""
    raise CliError(f"[ERROR] Owner '{owner_name}' not found.{hint}")


def _normalize_title(title: str) -> str:
    return " ".join((title or "").strip().lower().split())


def _find_duplicate_title_candidates(
    title: str, limit: int = 5
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (exact, similar) duplicate candidates for a card title."""
    normalized_target = _normalize_title(title)
    if not normalized_target:
        return [], []

    result = list_cards(search_filter=title, archived=False)
    cards = result.get("card", {})

    exact: list[dict[str, Any]] = []
    similar: list[dict[str, Any]] = []
    for cid, card in cards.items():
        existing_title = (card.get("title") or "").strip()
        if not existing_title:
            continue
        normalized_existing = _normalize_title(existing_title)
        if not normalized_existing:
            continue

        status = card.get("status") or "unknown"
        row: dict[str, Any] = {"id": cid, "title": existing_title, "status": status}
        if normalized_existing == normalized_target:
            exact.append(row)
            continue

        score = SequenceMatcher(None, normalized_target, normalized_existing).ratio()
        if (
            normalized_target in normalized_existing
            or normalized_existing in normalized_target
            or score >= 0.88
        ):
            row["score"] = score
            similar.append(row)

    similar.sort(key=lambda item: item.get("score", 0), reverse=True)
    return exact[:limit], similar[:limit]


def _guard_duplicate_title(
    title: str, allow_duplicate: bool = False, context: str = "card"
) -> list[str]:
    """Fail on exact duplicates and warn on near matches unless explicitly allowed.

    Returns:
        list of warning strings (empty if no near matches found).
    """
    if allow_duplicate:
        return []

    exact, similar = _find_duplicate_title_candidates(title)
    if exact:
        preview = ", ".join(
            f"{item['id']} ('{item['title']}', status={item['status']})" for item in exact
        )
        raise CliError(
            f"[ERROR] Duplicate {context} title detected: '{title}'.\n"
            f"[ERROR] Existing: {preview}\n"
            "[ERROR] Re-run with --allow-duplicate to bypass this check."
        )

    warnings: list[str] = []
    if similar:
        preview = ", ".join(
            f"{item['id']} ('{item['title']}', status={item['status']})" for item in similar
        )
        warnings.append(f"Similar {context} titles found for '{title}': {preview}")
    return warnings


def _rollback_created(created_ids: list[str]) -> tuple[list[str], list[str]]:
    """Archive created cards in reverse order for rollback. Returns (rolled_back, failed)."""
    rolled_back: list[str] = []
    rollback_failed: list[str] = []
    for cid in reversed(created_ids):
        try:
            archive_card(cid)
            rolled_back.append(cid)
        except Exception:
            rollback_failed.append(cid)
    return rolled_back, rollback_failed


# ---------------------------------------------------------------------------
# Content analysis helpers for split-features
# ---------------------------------------------------------------------------


def _classify_checklist_item(text: str) -> str | None:
    """Score a checklist item against lane keywords, return highest lane or None."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for lane_name, kw_list in keywords_map().items():
        score = sum(1 for kw in kw_list if kw in lower)
        if score > 0:
            scores[lane_name] = score
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def _analyze_feature_for_lanes(
    content: str, *, included_lanes: set[str] | None = None
) -> dict[str, list[str]]:
    """Parse checklist items from card content and classify into lanes.

    Handles both ``- []`` (Codecks interactive) and ``- [ ]`` (markdown) formats.
    Unclassified items go to the smallest lane. Empty lanes get generic defaults.

    Args:
        content: Card content text with checklist items.
        included_lanes: Set of lane names to include. If None, includes all
            required lanes plus no optional lanes (for backward compat with
            old include_art=True default, art is included by default).
    """
    import re

    if included_lanes is None:
        # Default: required lanes + art (backward compat)
        included_lanes = {lane.name for lane in LANES if lane.required}
        included_lanes.add("art")

    lanes: dict[str, list[str]] = {name: [] for name in included_lanes}

    items: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        match = re.match(r"^-\s*\[[\sx]?\]\s*(.+)", stripped)
        if match:
            items.append(match.group(1).strip())

    unclassified: list[str] = []
    for item in items:
        lane = _classify_checklist_item(item)
        if lane and lane in lanes:
            lanes[lane].append(item)
        else:
            unclassified.append(item)

    # Distribute unclassified items to the smallest lane
    for item in unclassified:
        smallest = min(lanes, key=lambda k: len(lanes[k]))
        lanes[smallest].append(item)

    # Fill empty lanes with generic defaults from registry
    all_defaults = defaults_map()
    for lane_name in lanes:
        if not lanes[lane_name]:
            lanes[lane_name] = list(all_defaults.get(lane_name, [f"Complete {lane_name} tasks"]))

    return lanes


# ---------------------------------------------------------------------------
# scaffold_feature
# ---------------------------------------------------------------------------


def scaffold_feature(
    title: str,
    *,
    hero_deck: str,
    code_deck: str,
    design_deck: str,
    art_deck: str | None = None,
    skip_art: bool = False,
    audio_deck: str | None = None,
    skip_audio: bool = False,
    description: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    effort: int | None = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Scaffold a Hero feature with lane sub-cards.

    Creates a Hero card plus Code, Design, and optionally Art/Audio sub-cards.
    Transaction-safe: archives created cards on partial failure.
    """
    spec = FeatureSpec.from_kwargs(
        title,
        hero_deck=hero_deck,
        code_deck=code_deck,
        design_deck=design_deck,
        art_deck=art_deck,
        skip_art=skip_art,
        audio_deck=audio_deck,
        skip_audio=skip_audio,
        description=description,
        owner=owner,
        priority=priority,
        effort=effort,
        allow_duplicate=allow_duplicate,
    )

    hero_title = f"Feature: {spec.title}"
    warnings = _guard_duplicate_title(
        hero_title,
        allow_duplicate=spec.allow_duplicate,
        context="feature hero",
    )

    hero_deck_id = resolve_deck_id(spec.hero_deck)

    # Resolve lane deck IDs from registry
    lane_deck_ids: dict[str, str | None] = {}
    for lane_def in LANES:
        deck_val = spec.lane_decks.get(lane_def.name)
        lane_deck_ids[lane_def.name] = resolve_deck_id(deck_val) if deck_val else None

    owner_id = _resolve_owner_id(spec.owner) if spec.owner else None
    pri = None if spec.priority == "null" else spec.priority
    common_update: dict[str, Any] = {}
    if owner_id:
        common_update["assigneeId"] = owner_id
    if pri is not None:
        common_update["priority"] = pri
    if spec.effort is not None:
        common_update["effort"] = spec.effort

    lane_coverage = "/".join(lane_def.display_name for lane_def in LANES)
    hero_body = (
        (spec.description.strip() + "\n\n" if spec.description else "") + "Success criteria:\n"
        f"- [] Lane coverage agreed ({lane_coverage})\n"
        "- [] Acceptance criteria validated\n"
        "- [] Integration verified"
    )
    created: list[FeatureSubcard] = []
    created_ids: list[str] = []

    try:
        hero_result = create_card(hero_title, hero_body)
        hero_id = hero_result.get("cardId")
        if not hero_id:
            raise CliError("[ERROR] Hero creation failed: missing cardId.")
        created_ids.append(hero_id)
        update_card(hero_id, deckId=hero_deck_id, masterTags=list(HERO_TAGS), **common_update)

        def _make_sub(lane_def_inner, deck_id):
            sub_title = f"[{lane_def_inner.display_name}] {spec.title}"
            checklist_lines = lane_def_inner.default_checklist
            sub_body = (
                "Scope:\n"
                f"- {lane_def_inner.display_name} lane execution for feature goal\n\n"
                "Checklist:\n" + "\n".join(f"- [] {line}" for line in checklist_lines)
            )
            res = create_card(sub_title, sub_body)
            sub_id = res.get("cardId")
            if not sub_id:
                raise CliError(
                    f"[ERROR] {lane_def_inner.display_name} sub-card creation failed: "
                    "missing cardId."
                )
            created_ids.append(sub_id)
            update_card(
                sub_id,
                parentCardId=hero_id,
                deckId=deck_id,
                masterTags=list(lane_def_inner.tags),
                **common_update,
            )
            created.append(FeatureSubcard(lane=lane_def_inner.name, id=sub_id))

        for lane_def in LANES:
            skip = spec.lane_skips.get(lane_def.name, False)
            deck_id = lane_deck_ids[lane_def.name]
            if not skip and deck_id:
                _make_sub(lane_def, deck_id)

    except SetupError as err:
        rolled_back, rollback_failed = _rollback_created(created_ids)
        detail = (
            f"{err}\n[ERROR] Rollback archived {len(rolled_back)}/{len(created_ids)} created cards."
        )
        if rollback_failed:
            detail += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
        raise SetupError(detail) from err
    except Exception as err:
        rolled_back, rollback_failed = _rollback_created(created_ids)
        detail = (
            f"[ERROR] Feature scaffold failed: {err}\n"
            f"[ERROR] Rollback archived {len(rolled_back)}/{len(created_ids)} "
            "created cards."
        )
        if rollback_failed:
            detail += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
        raise CliError(detail) from err

    notes: list[str] = []
    for lane_def in LANES:
        if spec.lane_auto_skips.get(lane_def.name, False):
            notes.append(
                f"{lane_def.display_name} lane auto-skipped (no --{lane_def.name}-deck provided)."
            )
    if warnings:
        notes.extend(warnings)

    report_lane_decks: dict[str, str | None] = {}
    for lane_def in LANES:
        skip = spec.lane_skips.get(lane_def.name, False)
        report_lane_decks[lane_def.name] = None if skip else spec.lane_decks.get(lane_def.name)

    report = FeatureScaffoldReport(
        hero_id=hero_id,
        hero_title=hero_title,
        subcards=created,
        hero_deck=spec.hero_deck,
        lane_decks=report_lane_decks,
        notes=notes or None,
    )
    return report.to_dict()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# split_features
# ---------------------------------------------------------------------------


def split_features(
    client: Any,
    *,
    deck: str,
    code_deck: str,
    design_deck: str,
    art_deck: str | None = None,
    skip_art: bool = False,
    audio_deck: str | None = None,
    skip_audio: bool = False,
    priority: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Batch-split feature cards into discipline sub-cards.

    Args:
        client: CodecksClient instance (used for list_cards/get_card).
    """
    spec = SplitFeaturesSpec.from_kwargs(
        deck=deck,
        code_deck=code_deck,
        design_deck=design_deck,
        art_deck=art_deck,
        skip_art=skip_art,
        audio_deck=audio_deck,
        skip_audio=skip_audio,
        priority=priority,
        dry_run=dry_run,
    )

    # Resolve deck IDs upfront (fail fast)
    resolve_deck_id(spec.deck)  # validate source deck exists
    lane_deck_ids: dict[str, str | None] = {}
    for lane_def in LANES:
        deck_val = spec.lane_decks.get(lane_def.name)
        lane_deck_ids[lane_def.name] = resolve_deck_id(deck_val) if deck_val else None

    # Build active lane config from registry
    active_lanes = []
    for lane_def in LANES:
        skip = spec.lane_skips.get(lane_def.name, False)
        deck_id = lane_deck_ids[lane_def.name]
        if not skip and deck_id:
            active_lanes.append((lane_def, deck_id))

    # List cards in source deck (lightweight — no content fetched)
    result = client.list_cards(deck=spec.deck)
    all_cards = result.get("cards", [])

    details: list[SplitFeatureDetail] = []
    skipped: list[dict[str, Any]] = []
    notes: list[str] = []
    created_ids: list[str] = []

    for card in all_cards:
        cid = card.get("id", "")
        title = card.get("title", "")
        sub_count = card.get("sub_card_count") or 0

        # Skip cards that already have sub-cards
        if sub_count > 0:
            skipped.append({"id": cid, "title": title, "reason": "already has sub-cards"})
            continue

        # Fetch full content for analysis
        detail = client.get_card(cid, include_conversations=False)
        content = detail.get("content") or ""

        included_lane_names = {ld.name for ld, _did in active_lanes}
        lanes = _analyze_feature_for_lanes(content, included_lanes=included_lane_names)

        # Determine priority: override > parent's priority
        pri = None
        if spec.priority is not None:
            pri = None if spec.priority == "null" else spec.priority
        else:
            parent_pri = detail.get("priority")
            if parent_pri:
                pri = parent_pri

        if spec.dry_run:
            subs = []
            for lane_def, _deck_id in active_lanes:
                checklist = lanes.get(lane_def.name, [])
                sub_title = f"[{lane_def.display_name}] {title}"
                subs.append(FeatureSubcard(lane=lane_def.name, id="(dry-run)", title=sub_title))
                notes.append(f"  {lane_def.name}: {len(checklist)} items")
            details.append(
                SplitFeatureDetail(
                    feature_id=cid,
                    feature_title=title,
                    subcards=subs,
                )
            )
            continue

        # Live mode: create sub-cards
        try:
            feature_subs: list[FeatureSubcard] = []
            for lane_def, lane_deck_id in active_lanes:
                checklist = lanes.get(lane_def.name, [])
                sub_title = f"[{lane_def.display_name}] {title}"
                sub_body = (
                    "Scope:\n"
                    f"- {lane_def.display_name} lane execution for feature goal\n\n"
                    "Checklist:\n" + "\n".join(f"- [] {item}" for item in checklist)
                )
                res = create_card(sub_title, sub_body)
                sub_id = res.get("cardId")
                if not sub_id:
                    raise CliError(
                        f"[ERROR] {lane_def.name} sub-card creation failed: missing cardId."
                    )
                created_ids.append(sub_id)

                update_kwargs: dict[str, Any] = {
                    "parentCardId": cid,
                    "deckId": lane_deck_id,
                    "masterTags": list(lane_def.tags),
                }
                if pri is not None:
                    update_kwargs["priority"] = pri
                update_card(sub_id, **update_kwargs)

                feature_subs.append(FeatureSubcard(lane=lane_def.name, id=sub_id, title=sub_title))

            details.append(
                SplitFeatureDetail(
                    feature_id=cid,
                    feature_title=title,
                    subcards=feature_subs,
                )
            )
        except SetupError as err:
            rolled_back, rollback_failed = _rollback_created(created_ids)
            detail_msg = (
                f"{err}\n[ERROR] Rollback archived "
                f"{len(rolled_back)}/{len(created_ids)} created cards."
            )
            if rollback_failed:
                detail_msg += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
            raise SetupError(detail_msg) from err
        except Exception as err:
            rolled_back, rollback_failed = _rollback_created(created_ids)
            detail_msg = (
                f"[ERROR] Split-features failed: {err}\n"
                f"[ERROR] Rollback archived {len(rolled_back)}/{len(created_ids)} "
                "created cards."
            )
            if rollback_failed:
                detail_msg += f"\n[ERROR] Rollback failed for: {', '.join(rollback_failed)}"
            raise CliError(detail_msg) from err

    total_subs = sum(len(d.subcards) for d in details)
    for lane_def in LANES:
        if spec.lane_skips.get(lane_def.name, False):
            notes.append(f"{lane_def.display_name} lane skipped.")

    report = SplitFeaturesReport(
        features_processed=len(details),
        features_skipped=len(skipped),
        subcards_created=total_subs if not spec.dry_run else 0,
        details=details,
        skipped=skipped,
        notes=notes or None,
    )
    return report.to_dict()  # type: ignore[no-any-return]
