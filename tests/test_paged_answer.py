"""`PagedAnswer` — the one envelope for the nine `mesh:mfg*` verbs (ADR-0070 section 3). See
`iagent_mesh/paged_answer.py`'s module docstring for the envelope's verbatim shape and the
`reason`/`withheld`/`as_of`/`as_of_unavailable`/`as_of_source` design notes this module's tests
exercise.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.paged_answer import (
    AnswerProvenance,
    Downsample,
    PagedAnswer,
    RowCitation,
    SuppressedStatistic,
)


def _provenance(**overrides) -> AnswerProvenance:
    fields = {"issued_at": "2026-11-15T00:00:00Z", "as_of": "2026-11-15T00:00:00Z"}
    fields.update(overrides)
    return AnswerProvenance(**fields)


def test_row_citation_requires_all_three_fields():
    with pytest.raises(ValidationError):
        RowCitation(source="serial_unit", record_id="abc")  # missing extracted_at


def test_row_citation_rejects_blank_fields():
    with pytest.raises(ValidationError):
        RowCitation(source="", record_id="abc", extracted_at="2026-11-15T00:00:00Z")


def test_suppressed_statistic_requires_statistic_and_reason():
    with pytest.raises(ValidationError):
        SuppressedStatistic(statistic="Cpk")  # missing reason
    stat = SuppressedStatistic(statistic="Cpk", reason="limit is non-numeric")
    assert stat.statistic == "Cpk"
    assert stat.reason == "limit is non-numeric"


def test_downsample_to_n_cannot_exceed_from_n():
    with pytest.raises(ValidationError):
        Downsample(from_n=100, to_n=200)


def test_downsample_rejects_negative_counts():
    with pytest.raises(ValidationError):
        Downsample(from_n=-1, to_n=0)


def test_downsample_accepts_equal_counts_as_no_downsampling():
    ds = Downsample(from_n=500, to_n=500)
    assert ds.from_n == ds.to_n == 500


def test_answer_provenance_issued_at_is_required():
    with pytest.raises(ValidationError):
        AnswerProvenance(dataset_urn="urn:dataset:serial_unit")  # missing issued_at


def test_answer_provenance_dataset_urn_and_ticket_id_default_to_none():
    provenance = _provenance()
    assert provenance.dataset_urn is None
    assert provenance.ticket_id is None
    assert provenance.as_of_unavailable is None
    assert provenance.as_of_source is None
    assert provenance.issued_at == "2026-11-15T00:00:00Z"


def test_answer_provenance_rejects_blank_optional_fields():
    with pytest.raises(ValidationError):
        _provenance(dataset_urn="")


def test_answer_provenance_as_of_is_required_no_default():
    # 0.9.27: omitting the key is no longer the same as stating absence — a caller must say
    # as_of=None, not leave the field out, so a never-set as_of can't read like a read-and-absent
    # one.
    with pytest.raises(ValidationError):
        AnswerProvenance(issued_at="2026-11-15T00:00:00Z")  # missing as_of


def test_answer_provenance_absent_as_of_with_no_reason_is_the_blank_the_ruling_forbids():
    # The architect's 11-20 ruling: "when an as-of is unavailable, say so; never show a blank."
    with pytest.raises(ValidationError):
        _provenance(as_of=None)  # as_of_unavailable also None


def test_answer_provenance_as_of_unavailable_says_why_as_of_is_absent():
    provenance = _provenance(as_of=None, as_of_unavailable="no_reader_for_source_type")
    assert provenance.as_of is None
    assert provenance.as_of_unavailable == "no_reader_for_source_type"


def test_answer_provenance_as_of_unavailable_cannot_ride_alongside_a_present_as_of():
    with pytest.raises(ValidationError):
        _provenance(as_of="2026-11-15T00:00:00Z", as_of_unavailable="reader_failed")


def test_answer_provenance_as_of_source_labels_a_present_as_of():
    provenance = _provenance(as_of_source="advertised_at_load")
    assert provenance.as_of == "2026-11-15T00:00:00Z"
    assert provenance.as_of_source == "advertised_at_load"


def test_answer_provenance_rejects_blank_as_of_unavailable_and_as_of_source():
    with pytest.raises(ValidationError):
        _provenance(as_of=None, as_of_unavailable="")
    with pytest.raises(ValidationError):
        _provenance(as_of_source="")


def test_paged_answer_requires_provenance():
    with pytest.raises(ValidationError):
        PagedAnswer()  # missing provenance, the envelope's only non-nullable field


def test_paged_answer_rows_next_rollup_reason_withheld_default_empty_or_none():
    answer = PagedAnswer(provenance=_provenance())
    assert answer.rows == ()
    assert answer.next is None
    assert answer.rollup is None
    assert answer.reason is None
    assert answer.withheld is None
    assert answer.suppressed == ()
    assert answer.downsampled is None


def test_paged_answer_empty_page_carries_a_reason_not_an_error():
    answer = PagedAnswer(reason="no_data", provenance=_provenance())
    assert answer.rows == ()
    assert answer.reason == "no_data"


def test_paged_answer_next_is_opaque_and_passed_through():
    answer = PagedAnswer(next="opaque-cursor-123", provenance=_provenance())
    assert answer.next == "opaque-cursor-123"


def test_paged_answer_rollup_and_withheld_carry_open_dicts():
    answer = PagedAnswer(
        rollup={"active": 12, "obsolete": 3},
        withheld={"level_2": True},
        provenance=_provenance(),
    )
    assert answer.rollup == {"active": 12, "obsolete": 3}
    assert answer.withheld == {"level_2": True}


def test_paged_answer_suppressed_holds_named_statistics():
    answer = PagedAnswer(
        suppressed=(SuppressedStatistic(statistic="Cpk", reason="limit is non-numeric"),),
        provenance=_provenance(),
    )
    assert [s.statistic for s in answer.suppressed] == ["Cpk"]


def test_paged_answer_downsampled_carries_from_n_to_n():
    answer = PagedAnswer(
        downsampled=Downsample(from_n=5000, to_n=500),
        provenance=_provenance(),
    )
    assert answer.downsampled.from_n == 5000
    assert answer.downsampled.to_n == 500


def test_paged_answer_rows_carry_whatever_generic_row_shape_the_caller_names():
    answer = PagedAnswer[dict](
        rows=({"part": "p1", "citation": RowCitation(
            source="serial_unit", record_id="u1", extracted_at="2026-11-15T00:00:00Z",
        )},),
        provenance=_provenance(),
    )
    assert len(answer.rows) == 1
    assert answer.rows[0]["part"] == "p1"


def test_paged_answer_is_frozen_and_forbids_unknown_fields():
    answer = PagedAnswer(provenance=_provenance())
    with pytest.raises(ValidationError):
        answer.reason = "no_data"
    with pytest.raises(ValidationError):
        PagedAnswer(provenance=_provenance(), extra_field="x")
