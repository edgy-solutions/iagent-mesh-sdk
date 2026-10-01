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
    USER_DROP,
    WAREHOUSE,
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


# ── the ordered tuple, and `user-drop` as its fifth, farthest rung (ADR-0041 §2) ──────────

def test_obtained_via_is_the_five_rung_tuple_ruled_by_adr_0041():
    """Pinned to the exact tuple ADR-0041 §2 rules, not a re-derivation of it — the order is
    meaningful (nearest-to-truth first) and this is the contract, not an implementation detail."""
    assert OBTAINED_VIA == (DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP)
    assert OBTAINED_VIA == ("direct", "etl", "warehouse", "manual-export", "user-drop")
    assert OBTAINED_VIA[-1] == USER_DROP, (
        "user-drop must be the FARTHEST rung — it is the degradation path a hand-carried "
        "document travelled, not a peer of etl or warehouse"
    )


def test_user_drop_is_a_legal_obtained_via_on_both_entry_points():
    block = make_provenance(**{**VALID, "obtained_via": USER_DROP, "as_of": AS_OF_UNKNOWN,
                                "standing": "supervised"})
    assert block["obtained_via"] == "user-drop"
    ProvenanceBlock(**{**VALID, "obtained_via": USER_DROP, "as_of": AS_OF_UNKNOWN,
                        "standing": "supervised"})  # does not raise


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
