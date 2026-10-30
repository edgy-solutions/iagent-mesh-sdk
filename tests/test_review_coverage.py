"""`ReviewCoverage`/`ReviewShapeRow` are typed exactly per Lane 1's (invincible-agent) wire-answer
packet to cortex-ui on the `review_coverage` rename — see
`sessions/2026-10-30-packet-to-cortex-cc-ca-from-lane-01-five-answers-review-coverage-0-4-73-wire.md`
in this repo, and the module docstring for the full ruling this type implements. This suite
covers: a full construction round-tripping via `.model_dump()`; the empty-collection defaults;
`ReviewCoverageSharedFact.bbox` rejecting an out-of-0..1 coordinate the same way
`EvidenceRef.bbox` does (`tests/test_provenance.py`); `ReviewShapeRow` with both an empty and a
populated `rules` list; and the open-vocabulary design of `rule`/`key`/`item_kind`/
`review_shape` — none of them a closed set this SDK validates against, same "ruled optional/open,
not required/closed" precedent `iagent_mesh.ingest`'s own fields already drew (see
`test_arrives_as_is_an_open_vocabulary_not_a_closed_enum` in `tests/test_ingest.py`).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.review_coverage import (
    ReviewCoverage,
    ReviewCoverageGroup,
    ReviewCoverageSharedFact,
    ReviewShapeRow,
    ReviewShapeRule,
)


def test_a_full_review_coverage_round_trips_via_model_dump():
    coverage = ReviewCoverage(
        review_shape="notice",
        item_kind="part",
        rules_version="notice.v1",
        looked_at=["0", "1", "2"],
        sampled=["0", "1"],
        flagged=["2"],
        groups=[ReviewCoverageGroup(rule="same_shape_run", key="run-a", items=["0", "1"])],
        shared=[
            ReviewCoverageSharedFact(
                rule="same_inherited_crop",
                page=3,
                bbox=(0.1, 0.2, 0.6, 0.7),
                items=["0", "1", "2"],
                confirmed=True,
            )
        ],
        sample={"strategy": "all_up_to", "n": 4},
    )
    dumped = coverage.model_dump()
    assert dumped == {
        "review_shape": "notice",
        "item_kind": "part",
        "rules_version": "notice.v1",
        "looked_at": ["0", "1", "2"],
        "sampled": ["0", "1"],
        "flagged": ["2"],
        "groups": [{"rule": "same_shape_run", "key": "run-a", "items": ["0", "1"]}],
        "shared": [
            {
                "rule": "same_inherited_crop",
                "page": 3,
                "bbox": (0.1, 0.2, 0.6, 0.7),
                "items": ["0", "1", "2"],
                "confirmed": True,
            }
        ],
        "sample": {"strategy": "all_up_to", "n": 4},
    }


def test_review_coverage_collection_fields_default_to_empty():
    coverage = ReviewCoverage(
        review_shape="notice", item_kind="part", rules_version="notice.v1"
    )
    assert coverage.looked_at == []
    assert coverage.sampled == []
    assert coverage.flagged == []
    assert coverage.groups == []
    assert coverage.shared == []
    assert coverage.sample is None


# ── ReviewCoverageSharedFact.bbox — same 0..1 page-fraction convention as EvidenceRef.bbox ──


def test_shared_fact_bbox_must_be_a_page_fraction():
    # the 2026-10-21 ruling EvidenceRef.bbox already follows: 0..1 only — anything outside is
    # unconverted pixel/point geometry, not a citation this type accepts.
    with pytest.raises(ValidationError, match="bbox"):
        ReviewCoverageSharedFact(
            rule="same_inherited_crop",
            page=3,
            bbox=(-0.1, 0.2, 0.6, 0.7),
            items=["0"],
            confirmed=False,
        )
    with pytest.raises(ValidationError, match="bbox"):
        ReviewCoverageSharedFact(
            rule="same_inherited_crop",
            page=3,
            bbox=(0.1, 0.2, 1.6, 0.7),
            items=["0"],
            confirmed=False,
        )


def test_shared_fact_bbox_must_have_positive_area():
    with pytest.raises(ValidationError, match="bbox"):
        ReviewCoverageSharedFact(
            rule="same_inherited_crop",
            page=3,
            bbox=(0.1, 0.2, 0.1, 0.7),  # x1 == x0
            items=["0"],
            confirmed=False,
        )


# ── ReviewShapeRow — seeded with rules: [], and populated (the notice.yaml example, §4) ──


def test_review_shape_row_with_no_rules_yet():
    row = ReviewShapeRow(
        review_shape="course", item_kind="concept", rules_version="course.v1"
    )
    assert row.rules == []
    assert row.params == {}


def test_review_shape_row_with_populated_rules():
    row = ReviewShapeRow(
        review_shape="notice",
        item_kind="part",
        rules_version="notice.v1",
        params={"sample_all_up_to": 4},
        rules=[
            ReviewShapeRule(id="same_shape_run", params={"min_run": 3, "per_run": 2}),
            ReviewShapeRule(id="same_inherited_crop", params={}),
        ],
    )
    assert row.params == {"sample_all_up_to": 4}
    assert [r.id for r in row.rules] == ["same_shape_run", "same_inherited_crop"]
    assert row.rules[0].params == {"min_run": 3, "per_run": 2}
    assert row.rules[1].params == {}


# ── open vocabulary: rule / key / item_kind / review_shape are not a closed set ──


def test_rule_key_item_kind_review_shape_are_an_open_vocabulary_not_a_closed_enum():
    """None of `rule`, `key`, `item_kind`, `review_shape` is restricted to any particular set —
    a new rule, grouping key, item kind or review shape is a `policy/review_shapes/<shape>.yaml`
    registry row, not an SDK release (the wire packet's §4; the module docstring's
    generic-at-birth note)."""
    coverage = ReviewCoverage(
        review_shape="a-brand-new-shape",
        item_kind="a-brand-new-item-kind",
        rules_version="v99",
        groups=[ReviewCoverageGroup(rule="a-brand-new-rule", key="a-brand-new-key", items=[])],
    )
    assert coverage.review_shape == "a-brand-new-shape"
    assert coverage.item_kind == "a-brand-new-item-kind"
    assert coverage.groups[0].rule == "a-brand-new-rule"
    assert coverage.groups[0].key == "a-brand-new-key"
