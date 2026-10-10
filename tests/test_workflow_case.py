"""Seals for the 0.9.9 ADR-0039 case runner record — `WorkflowCaseRecord` and its nested rows.
One seal per ruling the module docstring states, so a later edit that quietly reverses a ruling
fails here first.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.workflow_case import (
    CaseInputRevision,
    CaseInstanceRef,
    CaseTransition,
    WorkflowCaseRecord,
)


def _record(**overrides) -> WorkflowCaseRecord:
    fields = dict(case_id="case-1", trigger="fault-reported")
    fields.update(overrides)
    return WorkflowCaseRecord(**fields)


def test_a_bare_record_is_valid_before_any_transition_has_run():
    """THE RULING THIS SEALS: `input_revisions` defaults to `()` rather than being required,
    because the real case dict does not carry the key until after its first `_record` call — a
    record observed between construction and that first call is a real state, not a gap."""
    rec = _record()
    assert rec.state is None
    assert rec.terminal is None
    assert rec.episode is None
    assert rec.instances == ()
    assert rec.transitions == ()
    assert rec.input_revisions == ()


def test_state_and_terminal_accept_an_arbitrary_definition_id_string():
    """THE RULING THIS SEALS: `state`/`terminal` are plain `Optional[str]`, never a closed
    `CaseState`-style Literal — a workflow-defined `definition_id` the chaining tables name is
    not a value this type can enumerate in advance."""
    rec = _record(state="safety-check-instance-1", terminal="released-to-service")
    assert rec.state == "safety-check-instance-1"
    assert rec.terminal == "released-to-service"


def test_case_state_is_not_importable_from_this_module():
    """THE RULING THIS SEALS, STATED AS A NEGATIVE: `CaseState` lives in iagent, not here, and is
    a different concept from `WorkflowCaseRecord.state` besides — this module must not define or
    re-export anything by that name."""
    import iagent_mesh.workflow_case as m
    assert not hasattr(m, "CaseState")
    assert "CaseState" not in m.__all__


def test_a_transition_round_trips_the_wire_s_from_key_through_the_frm_alias():
    """THE RULING THIS SEALS: `frm` is the field name (mirroring `_record`'s own parameter), but
    the wire's `"from"` key is what the alias serializes to and validates from."""
    t = CaseTransition.model_validate(
        {"from": "received", "outcome": "triaged", "to": "triaged", "by": "system",
         "at": "2026-10-06T00:00:00Z"}
    )
    assert t.frm == "received"
    dumped = t.model_dump(by_alias=True)
    assert dumped["from"] == "received"
    assert "frm" not in dumped


def test_a_transition_is_also_constructible_by_the_field_name_frm():
    """`populate_by_name=True` — the ergonomic escape hatch from a reserved-keyword wire key."""
    t = CaseTransition(frm=None, outcome="received", to="received", at="2026-10-06T00:00:00Z")
    assert t.frm is None


def test_the_first_transition_s_frm_is_none_not_a_required_string():
    """THE RULING THIS SEALS: `_record(ctx, case, frm=None, ...)` opens every case — the case's
    very first transition has no prior state, and `frm` must accept that rather than demanding a
    non-blank string the way `outcome`/`to`/`at` do."""
    t = CaseTransition(frm=None, outcome="received", to="received", at="2026-10-06T00:00:00Z")
    assert t.frm is None


def test_a_transition_s_outcome_to_and_at_cannot_be_blank():
    with pytest.raises(ValidationError, match="outcome='' — required"):
        CaseTransition(frm=None, outcome="", to="received", at="2026-10-06T00:00:00Z")


def test_a_transition_rejects_an_extra_key_beyond_the_three_record_actually_sends():
    """THE RULING THIS SEALS: `instance_id`/`decided_by`/`input_revision` are the only three
    `**extra` keys `_record` is ever called with — a fourth is a runner change this model has
    not seen, and `extra='forbid'` must reject it rather than silently accept it."""
    with pytest.raises(ValidationError):
        CaseTransition(
            frm=None, outcome="received", to="received", at="2026-10-06T00:00:00Z",
            unexpected_fourth_key="surprise",
        )


def test_an_input_revision_s_provenance_is_closed_to_pushed_or_pulled():
    """THE RULING THIS SEALS: there are only two sources a revision can come from; a third is a
    runner change, not a row anyone writes."""
    CaseInputRevision(rev=1, event_id="e", received_at="2026-10-06T00:00:00Z", provenance="pushed")
    CaseInputRevision(rev=2, event_id="e", received_at="2026-10-06T00:00:01Z", provenance="pulled")
    with pytest.raises(ValidationError):
        CaseInputRevision(
            rev=3, event_id="e", received_at="2026-10-06T00:00:02Z", provenance="sideways"
        )


def test_a_case_instance_ref_is_1_indexed():
    CaseInstanceRef(n=1, instance_id="case-1~1", definition_id="safety-check")
    with pytest.raises(ValidationError, match="n=0"):
        CaseInstanceRef(n=0, instance_id="case-1~0", definition_id="safety-check")


def test_a_full_record_assembles_from_dicts_the_way_the_runner_builds_them():
    """End-to-end: the shape `_run_case` actually produces, dict-first, the way `ctx.set("case",
    case)` and a replay would hand it back."""
    rec = _record(
        state="triaged", episode="ep-1",
        instances=[{"n": 1, "instance_id": "case-1~1", "definition_id": "safety-check"}],
        transitions=[
            {"from": None, "outcome": "received", "to": "received", "by": "system",
             "at": "2026-10-06T00:00:00Z", "reason": None},
            {"from": "received", "outcome": "triaged", "to": "triaged", "by": "system",
             "at": "2026-10-06T00:00:01Z", "reason": None},
        ],
        input_revisions=[
            {"rev": 1, "event_id": "case-1", "received_at": "2026-10-06T00:00:00Z",
             "provenance": "pushed"},
        ],
    )
    assert rec.instances[0].definition_id == "safety-check"
    assert rec.transitions[1].frm == "received"
    assert rec.input_revisions[0].provenance == "pushed"


def test_case_id_and_trigger_cannot_be_blank():
    with pytest.raises(ValidationError, match="case_id='' — required"):
        _record(case_id="")
    with pytest.raises(ValidationError, match="trigger='' — required"):
        _record(trigger="")


def test_the_record_itself_rejects_an_unknown_top_level_key():
    with pytest.raises(ValidationError):
        WorkflowCaseRecord(case_id="c", trigger="t", status="CLOSED")
