"""The provenance block's job is a refusal: a claim without complete provenance does not get
written. That refusal has to survive TWO different entry points — the builder
(:func:`make_provenance`, the one doc-tools imports) and the typed model
(:class:`ProvenanceBlock`, for a caller who already has the fields in hand) — and it has to
survive them with DIFFERENT exception shapes on purpose. This file's spine is proving that
difference is real rather than a claim in a docstring.

A refusal suite with no positive control is the failure it is testing for. VALID is that
control, exercised first, for both entry points.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.provenance import (
    AS_OF_UNKNOWN,
    DIRECT,
    ETL,
    MANUAL_EXPORT,
    OBTAINED_VIA,
    STEWARD_CORRECTED,
    STEWARD_ENTERED,
    USER_DROP,
    WAREHOUSE,
    EvidenceRef,
    ExtractionDefect,
    ProvenanceBlock,
    ProvenanceIncomplete,
    is_stale,
    make_provenance,
    require_provenance,
    validate_provenance,
)

VALID = dict(
    authoritative_source="vendor-pcn-feed",
    obtained_via=DIRECT,
    as_of="2026-09-30",
    ingested_at="2026-09-30T12:00:00Z",
    ingest_run="run-001",
    standing="trusted",
)


# ── the positive controls ────────────────────────────────────────────────────────────────

def test_make_provenance_builds_the_six_required_fields():
    block = make_provenance(**VALID)
    assert block == VALID
    assert "derived_from" not in block


def test_provenance_block_builds_and_matches_make_provenance():
    """THE CLAIM EXERCISED, NOT ASSERTED. The model docstring says `as_dict()` returns exactly
    what `make_provenance` returns "so a consumer written against either shape reads the same
    keys" — a comment asserting an effect is not evidence, so this compares the two outputs for
    the identical inputs rather than trusting the docstring."""
    block = ProvenanceBlock(**VALID)
    assert block.as_dict() == make_provenance(**VALID)


def test_derived_from_appears_only_when_set():
    with_derivation = make_provenance(**VALID, derived_from="urn:pcn:12345")
    assert with_derivation["derived_from"] == "urn:pcn:12345"
    assert "derived_from" not in make_provenance(**VALID)

    block = ProvenanceBlock(**VALID, derived_from="urn:pcn:12345")
    assert block.as_dict()["derived_from"] == "urn:pcn:12345"


def test_ingest_id_appears_only_when_set():
    """Same discipline as `derived_from`, same test shape — `ingest_id` is additive, optional,
    and present on the wire only when a caller actually names an ingest act."""
    with_ingest = make_provenance(**VALID, ingest_id="ingest-2026-09-30-001")
    assert with_ingest["ingest_id"] == "ingest-2026-09-30-001"
    assert "ingest_id" not in make_provenance(**VALID)

    block = ProvenanceBlock(**VALID, ingest_id="ingest-2026-09-30-001")
    assert block.as_dict()["ingest_id"] == "ingest-2026-09-30-001"
    assert "ingest_id" not in ProvenanceBlock(**VALID).as_dict()


# ── the ordered tuple, `user-drop` its fifth rung (ADR-0041 §2), `steward-corrected` its ────
# sixth (invincible-agent/lane/01's steward-correction ruling, 2026-10-10), `steward-entered` ─
# its seventh AND LAST (the architect's 2026-10-23 ruling on 208's empty-notice task) ─────────

def test_obtained_via_is_the_seven_rung_tuple_ruled_by_adr_0041_and_the_steward_rulings():
    """Pinned to the exact tuple all three rulings produce, not a re-derivation of it — the
    order is meaningful (nearest-to-truth first) and this is the contract, not an implementation
    detail."""
    assert OBTAINED_VIA == (
        DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP, STEWARD_CORRECTED, STEWARD_ENTERED,
    )
    assert OBTAINED_VIA == (
        "direct", "etl", "warehouse", "manual-export", "user-drop", "steward-corrected",
        "steward-entered",
    )
    assert OBTAINED_VIA[-1] == STEWARD_ENTERED, (
        "steward-entered must be the FARTHEST rung — an entered row has only the steward and "
        "a page, not even a reading to correct, which the 2026-10-23 ruling names as the last "
        "rung this vocabulary needs"
    )
    assert OBTAINED_VIA[-2] == STEWARD_CORRECTED, (
        "steward-corrected must still be the SECOND-farthest rung — appending steward-entered "
        "after it must not have reordered what was already there"
    )
    assert OBTAINED_VIA[-3] == USER_DROP, (
        "user-drop must still be the THIRD-farthest rung — appending steward-corrected and "
        "steward-entered after it must not have reordered what was already there"
    )


def test_user_drop_is_a_legal_obtained_via_on_both_entry_points():
    block = make_provenance(**{**VALID, "obtained_via": USER_DROP, "as_of": AS_OF_UNKNOWN,
                                "standing": "supervised"})
    assert block["obtained_via"] == "user-drop"
    ProvenanceBlock(**{**VALID, "obtained_via": USER_DROP, "as_of": AS_OF_UNKNOWN,
                        "standing": "supervised"})  # does not raise


_ENTERED_VALID = {**VALID, "obtained_via": STEWARD_ENTERED, "corrected_by": "alice"}


def test_steward_entered_is_a_legal_obtained_via_on_both_entry_points():
    """steward-entered rides through the SAME constructor as every other rung — no parallel
    path — but its own pairing is the MIRROR of steward-corrected's: corrected_by required,
    extracted_value forbidden (confirmed by the architect, same day, to both lanes)."""
    block = make_provenance(**_ENTERED_VALID)
    assert block["obtained_via"] == "steward-entered"
    assert block["corrected_by"] == "alice"
    assert "extracted_value" not in block
    pb = ProvenanceBlock(**_ENTERED_VALID)  # does not raise
    assert pb.as_dict()["corrected_by"] == "alice"
    assert "extracted_value" not in pb.as_dict()


def test_steward_entered_requires_corrected_by():
    bad = {k: v for k, v in _ENTERED_VALID.items() if k != "corrected_by"}
    with pytest.raises(ProvenanceIncomplete, match="corrected_by"):
        make_provenance(**bad)
    with pytest.raises(ValidationError):
        ProvenanceBlock(**bad)


def test_steward_entered_forbids_extracted_value():
    """The mirror image of steward-corrected's requirement — there was no extraction for an
    entered row to differ from."""
    bad = {**_ENTERED_VALID, "extracted_value": "F-16"}
    with pytest.raises(ProvenanceIncomplete, match="extracted_value"):
        make_provenance(**bad)
    with pytest.raises(ValidationError):
        ProvenanceBlock(**bad)


# ── `steward-corrected`, its `corrected_by`/`extracted_value` pairing, both entry points ──

_STEWARD_VALID = {
    **VALID, "obtained_via": STEWARD_CORRECTED,
    "corrected_by": "bob", "extracted_value": "F-16",
}


def test_steward_corrected_is_a_legal_obtained_via_on_both_entry_points():
    block = make_provenance(**_STEWARD_VALID)
    assert block["obtained_via"] == "steward-corrected"
    assert block["corrected_by"] == "bob"
    assert block["extracted_value"] == "F-16"
    ProvenanceBlock(**_STEWARD_VALID)  # does not raise


def test_extracted_value_may_be_blank_the_defect_can_be_that_nothing_was_extracted():
    block = make_provenance(**{**_STEWARD_VALID, "extracted_value": ""})
    assert block["extracted_value"] == ""
    pb = ProvenanceBlock(**{**_STEWARD_VALID, "extracted_value": ""})
    assert pb.as_dict()["extracted_value"] == ""


def test_corrected_by_and_extracted_value_are_REQUIRED_together_under_steward_corrected():
    for missing in ("corrected_by", "extracted_value"):
        bad = {k: v for k, v in _STEWARD_VALID.items() if k != missing}
        with pytest.raises(ProvenanceIncomplete, match=missing):
            make_provenance(**bad)
        with pytest.raises(ValidationError):
            ProvenanceBlock(**bad)


def test_corrected_by_and_extracted_value_are_REFUSED_under_any_other_rung():
    """steward-entered is excluded here — its own pairing (corrected_by required, extracted_value
    forbidden) is the mirror of this one, not a member of it. See the steward-entered tests
    above."""
    for rung in (DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP):
        bad = {**VALID, "obtained_via": rung, "corrected_by": "bob", "extracted_value": "x"}
        if rung == USER_DROP:
            bad["as_of"] = AS_OF_UNKNOWN
            bad["standing"] = "supervised"
        with pytest.raises(ProvenanceIncomplete, match="corrected_by"):
            make_provenance(**bad)
        with pytest.raises(ValidationError):
            ProvenanceBlock(**bad)


def test_validate_provenance_enforces_the_same_pairing_on_the_dict_path():
    validate_provenance(make_provenance(**_STEWARD_VALID))  # does not raise
    with pytest.raises(ProvenanceIncomplete, match="corrected_by"):
        validate_provenance({**VALID, "corrected_by": "bob", "extracted_value": "x"})
    with pytest.raises(ProvenanceIncomplete, match="corrected_by"):
        validate_provenance({**_STEWARD_VALID, "corrected_by": None})


def test_validate_provenance_enforces_the_steward_entered_pairing_on_the_dict_path():
    validate_provenance(make_provenance(**_ENTERED_VALID))  # does not raise
    with pytest.raises(ProvenanceIncomplete, match="corrected_by"):
        validate_provenance({**VALID, "obtained_via": STEWARD_ENTERED})
    with pytest.raises(ProvenanceIncomplete, match="extracted_value"):
        validate_provenance({**_ENTERED_VALID, "extracted_value": "F-16"})


# ── ExtractionDefect, the companion admin-queue record the same ruling names ──────────────

_DEFECT_VALID = dict(
    artifact_id="artifact-1",
    pin_digest="pin-2026-10-10-001",
    extracted_value="F-35",
    corrected_value="F-16",
    evidence=("pin:pin-2026-10-10-001",),
)


def test_extraction_defect_builds_from_the_valid_fixture():
    d = ExtractionDefect(**_DEFECT_VALID)
    assert d.corrected_value == "F-16"
    assert d.evidence == ("pin:pin-2026-10-10-001",)


def test_extraction_defect_extracted_value_may_be_blank():
    """Same discipline as `ProvenanceBlock.extracted_value`: "nothing was extracted" is itself
    the defect, not an omission this field refuses."""
    ExtractionDefect(**{**_DEFECT_VALID, "extracted_value": ""})  # does not raise


def test_extraction_defect_required_strings_cannot_be_blank():
    for field in ("artifact_id", "pin_digest", "corrected_value"):
        with pytest.raises(ValidationError):
            ExtractionDefect(**{**_DEFECT_VALID, field: ""})


def test_extraction_defect_evidence_is_required_non_empty():
    with pytest.raises(ValidationError, match="evidence"):
        ExtractionDefect(**{**_DEFECT_VALID, "evidence": ()})


def test_extraction_defect_is_frozen_and_forbids_extra_fields():
    d = ExtractionDefect(**_DEFECT_VALID)
    with pytest.raises(ValidationError):
        d.corrected_value = "something-else"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ExtractionDefect(**_DEFECT_VALID, corrected_by="bob")  # type: ignore[call-arg]


# ── EvidenceRef, ADDED 0.9.11 — the structured sibling to evidence ───────────────────────
# bbox is a page fraction, 0..1, origin top-left (architect ruling 2026-10-21) — the fixture's
# coordinates are fractions of the page, never layout pixels or points.

_REF_VALID = dict(page=3, bbox=(0.1, 0.2, 0.6, 0.7))


def test_evidence_ref_builds_from_the_valid_fixture():
    ref = EvidenceRef(**_REF_VALID)
    assert ref.page == 3
    assert ref.bbox == (0.1, 0.2, 0.6, 0.7)


def test_evidence_ref_page_must_be_at_least_one():
    with pytest.raises(ValidationError, match="page"):
        EvidenceRef(**{**_REF_VALID, "page": 0})


def test_evidence_ref_bbox_must_have_positive_area():
    with pytest.raises(ValidationError, match="bbox"):
        EvidenceRef(**{**_REF_VALID, "bbox": (0.1, 0.2, 0.1, 0.7)})  # x1 == x0
    with pytest.raises(ValidationError, match="bbox"):
        EvidenceRef(**{**_REF_VALID, "bbox": (0.1, 0.2, 0.05, 0.7)})  # x1 < x0


def test_evidence_ref_bbox_must_be_a_page_fraction():
    # the 2026-10-21 ruling: 0..1 only — anything outside is unconverted pixel/point geometry.
    with pytest.raises(ValidationError, match="bbox"):
        EvidenceRef(**{**_REF_VALID, "bbox": (-0.1, 0.2, 0.6, 0.7)})  # x0 < 0
    with pytest.raises(ValidationError, match="bbox"):
        EvidenceRef(**{**_REF_VALID, "bbox": (0.1, 0.2, 1.6, 0.7)})  # x1 > 1
    with pytest.raises(ValidationError, match="bbox"):
        EvidenceRef(**{**_REF_VALID, "bbox": (10.0, 20.0, 110.0, 70.0)})  # layout pixels, unconverted


def test_evidence_ref_is_frozen_and_forbids_extra_fields():
    ref = EvidenceRef(**_REF_VALID)
    with pytest.raises(ValidationError):
        ref.page = 4  # type: ignore[misc]
    with pytest.raises(ValidationError):
        EvidenceRef(**_REF_VALID, bogus="x")  # type: ignore[call-arg]


def test_evidence_ref_note_defaults_to_none():
    ref = EvidenceRef(**_REF_VALID)
    assert ref.note is None


def test_evidence_ref_accepts_the_bff_s_free_string_as_note():
    # the architect's 2026-10-21 ruling: the SDK's {page, bbox} shape wins; the BFF's own free
    # string lands here as `note`, not as a second, looser shape for this model.
    ref = EvidenceRef(**_REF_VALID, note="page 1 column header 'Customer Part Number'")
    assert ref.note == "page 1 column header 'Customer Part Number'"


def test_evidence_ref_note_must_not_be_blank_when_given():
    with pytest.raises(ValidationError, match="note"):
        EvidenceRef(**_REF_VALID, note="   ")


def test_evidence_ref_bbox_may_be_null():
    # the architect's second 2026-10-21 ruling: null bbox means "stated on this page, no box
    # we can draw" — page stays required, bbox alone may be omitted.
    ref = EvidenceRef(page=3, bbox=None)
    assert ref.page == 3
    assert ref.bbox is None


def test_evidence_ref_page_is_still_required_when_bbox_is_null():
    with pytest.raises(ValidationError, match="page"):
        EvidenceRef(bbox=None)  # type: ignore[call-arg]


def test_extraction_defect_evidence_ref_defaults_to_none():
    d = ExtractionDefect(**_DEFECT_VALID)
    assert d.evidence_ref is None


def test_extraction_defect_accepts_a_structured_evidence_ref_alongside_evidence():
    d = ExtractionDefect(**{**_DEFECT_VALID, "evidence_ref": _REF_VALID})
    assert d.evidence_ref == EvidenceRef(**_REF_VALID)
    assert d.evidence == ("pin:pin-2026-10-10-001",)  # unchanged, still required


def test_an_unknown_obtained_via_is_refused_on_both_entry_points():
    with pytest.raises(ProvenanceIncomplete, match="obtained_via"):
        make_provenance(**{**VALID, "obtained_via": "carrier-pigeon"})
    with pytest.raises(ValidationError):
        ProvenanceBlock(**{**VALID, "obtained_via": "carrier-pigeon"})


# ── the deliberate divergence: ProvenanceIncomplete vs. ValidationError ───────────────────

def test_make_provenance_raises_PROVENANCE_INCOMPLETE_BY_NAME_not_a_generic_ValueError():
    """THE WRITE-SIDE GATE. A caller gating on "provenance was incomplete" (ADR-0035 §4) must
    be able to catch ProvenanceIncomplete specifically — not a bare ValueError that could be
    any of a dozen unrelated defects."""
    for missing in ("authoritative_source", "as_of", "ingest_run", "standing"):
        bad = {**VALID, missing: ""}
        with pytest.raises(ProvenanceIncomplete):
            make_provenance(**bad)


def test_provenance_block_raises_VALIDATION_ERROR_not_PROVENANCE_INCOMPLETE():
    """THE DESIGN LINE THIS MODULE DRAWS, PROVEN RATHER THAN DOCUMENTED. A bare-field refusal on
    the typed model goes through pydantic-core, which catches a ValueError raised inside a
    field_validator and re-wraps it as ValidationError — so ProvenanceIncomplete raised there
    would never reach a caller under its own name. The module docstring says this is why
    ProvenanceIncomplete is raised directly by the builder/gate functions instead; this is the
    arm that would catch a future edit wiring ProvenanceIncomplete into a field_validator by
    mistake, where it would silently stop being catchable by name."""
    for missing in ("authoritative_source", "as_of", "ingest_run", "standing"):
        bad = {**VALID, missing: ""}
        with pytest.raises(ValidationError) as exc_info:
            ProvenanceBlock(**bad)
        assert not issubclass(exc_info.type, ProvenanceIncomplete)


def test_validate_provenance_and_require_provenance_raise_PROVENANCE_INCOMPLETE():
    """The re-check path (a block that did not come from the builder) must refuse by the same
    name as the builder — a future writer bypassing the constructor gets the same gate."""
    with pytest.raises(ProvenanceIncomplete, match="must be a dict"):
        validate_provenance("not-a-block")
    with pytest.raises(ProvenanceIncomplete, match="missing"):
        validate_provenance({**VALID, "standing": ""})
    with pytest.raises(ProvenanceIncomplete):
        require_provenance({"provenance": {**VALID, "ingest_run": ""}})
    require_provenance({"provenance": VALID})  # does not raise


def test_validate_provenance_accepts_a_block_make_provenance_built():
    """Round trip: the builder's own output must satisfy the re-check path, or the two
    functions disagree about what "complete" means."""
    validate_provenance(make_provenance(**VALID))  # does not raise


# ── as_of, the sentinel, and staleness ─────────────────────────────────────────────────────

def test_as_of_unknown_is_required_not_a_blank():
    """A BLANK collapses 'we could not know' into 'we forgot to record'. Refused, distinctly
    from an omitted field, because the sentinel exists precisely so this distinction survives."""
    with pytest.raises(ProvenanceIncomplete, match="as_of"):
        make_provenance(**{**VALID, "as_of": ""})
    make_provenance(**{**VALID, "as_of": AS_OF_UNKNOWN})  # does not raise


def test_is_stale_returns_none_never_false_for_unknown_vintage():
    """THE OPTIMISTIC-DEFAULT ARM. Reporting an unknowable vintage as 'not stale' would be
    exactly the dishonest default this codebase keeps refusing — proven here, not assumed."""
    block = {**VALID, "as_of": AS_OF_UNKNOWN}
    result = is_stale(block, now_date="2026-09-30", max_age_days=30)
    assert result is None
    assert result is not False


def test_is_stale_true_past_the_window_false_within_it():
    stale = is_stale({**VALID, "as_of": "2026-01-01"}, now_date="2026-09-30", max_age_days=30)
    assert stale is True
    fresh = is_stale({**VALID, "as_of": "2026-09-29"}, now_date="2026-09-30", max_age_days=30)
    assert fresh is False


def test_is_stale_returns_none_not_false_on_an_unparseable_date():
    """An unparseable date is UNKNOWABLE, not fresh — same discipline as the sentinel case,
    exercised on a different way a date can fail to answer the question."""
    result = is_stale({**VALID, "as_of": "not-a-date"}, now_date="2026-09-30", max_age_days=30)
    assert result is None


# ── the model's own coherence ────────────────────────────────────────────────────────────

def test_provenance_block_is_frozen_and_forbids_extra_fields():
    block = ProvenanceBlock(**VALID)
    with pytest.raises(ValidationError):
        block.authoritative_source = "something-else"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ProvenanceBlock(**VALID, unexpected_field="x")
