"""Seals for the 0.9.9 ADR-0029/ADR-0039 process schema — `WorkflowDefinition`, its step kinds,
and `load_workflow_definition`. One seal per ruling the module docstring states, so a later edit
that quietly reverses a ruling fails here first.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.workflow_definition import (
    CompletionPolicy,
    DirectCallStep,
    DispatchFanoutStep,
    EmitStep,
    HumanAwaitStep,
    RenderStep,
    SignalAwaitStep,
    SpoOperationStep,
    WaitStep,
    WorkflowDefinition,
    WorkflowDefinitionError,
    load_workflow_definition,
)


def _definition(**overrides) -> WorkflowDefinition:
    fields = dict(
        id="safety-check",
        name="Safety Check",
        steps=[{"kind": "wait", "id": "settle", "seconds": 60}],
    )
    fields.update(overrides)
    return WorkflowDefinition(**fields)


# ── WorkflowDefinition top level ────────────────────────────────────────────────────────────

def test_a_minimal_definition_is_valid():
    d = _definition()
    assert d.id == "safety-check"
    assert d.classification is None
    assert d.participants == ()
    assert d.domain_stages == ()
    assert d.observable_state is None
    assert len(d.steps) == 1


def test_id_and_name_cannot_be_blank():
    with pytest.raises(ValidationError, match="id='' — required"):
        _definition(id="")
    with pytest.raises(ValidationError, match="name='' — required"):
        _definition(name="")


def test_steps_cannot_be_empty():
    with pytest.raises(ValidationError):
        _definition(steps=[])


def test_an_unknown_step_kind_fails_the_discriminator_loudly():
    with pytest.raises(ValidationError):
        _definition(steps=[{"kind": "mystery", "id": "x"}])


def test_the_definition_itself_rejects_an_unknown_top_level_key():
    with pytest.raises(ValidationError):
        WorkflowDefinition(
            id="d", name="D", steps=[{"kind": "wait", "id": "w", "seconds": 1}],
            status="DRAFT",
        )


def test_duplicate_step_ids_are_refused():
    with pytest.raises(ValidationError, match="duplicate step ids"):
        _definition(
            steps=[
                {"kind": "wait", "id": "same", "seconds": 1},
                {"kind": "wait", "id": "same", "seconds": 2},
            ]
        )


def test_two_human_awaits_sharing_a_resolved_promise_name_are_refused():
    with pytest.raises(ValidationError, match="promise names awaited twice"):
        _definition(
            steps=[
                {"kind": "human_await", "id": "a", "audience": "promotion:X",
                 "promise_name": "shared"},
                {"kind": "human_await", "id": "b", "audience": "promotion:X",
                 "promise_name": "shared"},
            ]
        )


def test_default_promise_names_still_collide_if_step_ids_matched_elsewhere():
    # Two DIFFERENT step ids, same explicit promise_name: distinct ids pass the id check, but the
    # shared promise name must still be caught.
    with pytest.raises(ValidationError, match="promise names awaited twice"):
        _definition(
            steps=[
                {"kind": "human_await", "id": "approve-1", "audience": "promotion:X"},
                {"kind": "human_await", "id": "approve-2", "audience": "promotion:X",
                 "promise_name": "approval_approve-1"},
            ]
        )


def test_case_execution_concepts_have_no_counterpart_here():
    """THE RULING THIS SEALS: a WorkflowDefinition carries no execution state — CaseState and
    WorkflowCaseRecord.state/.terminal have no counterpart in this module."""
    d = _definition()
    assert not hasattr(d, "state")
    assert not hasattr(d, "terminal")
    import iagent_mesh.workflow_definition as m
    assert not hasattr(m, "CaseState")
    assert not hasattr(m, "WorkflowCaseRecord")


# ── CompletionPolicy ─────────────────────────────────────────────────────────────────────────

def test_n_of_m_quorum_requires_a_threshold_of_at_least_two():
    CompletionPolicy(quorum="n_of_m", threshold=2)
    with pytest.raises(ValidationError, match="requires a threshold"):
        CompletionPolicy(quorum="n_of_m", threshold=1)
    with pytest.raises(ValidationError, match="requires a threshold"):
        CompletionPolicy(quorum="n_of_m")


def test_threshold_is_meaningless_without_n_of_m():
    with pytest.raises(ValidationError, match="only meaningful with quorum"):
        CompletionPolicy(quorum="any_of", threshold=2)


# ── HumanAwaitStep ───────────────────────────────────────────────────────────────────────────

def test_human_await_resolved_promise_name_defaults_to_approval_prefixed_id():
    step = HumanAwaitStep(kind="human_await", id="approve-1", audience="promotion:X")
    assert step.resolved_promise_name() == "approval_approve-1"


def test_human_await_resolved_promise_name_honours_an_explicit_override():
    step = HumanAwaitStep(
        kind="human_await", id="approve-1", audience="promotion:X", promise_name="decision",
    )
    assert step.resolved_promise_name() == "decision"


def test_human_await_approves_requires_a_role():
    with pytest.raises(ValidationError, match="requires a `role`"):
        HumanAwaitStep(
            kind="human_await", id="a", audience="promotion:X", approves=["accept"],
        )
    HumanAwaitStep(
        kind="human_await", id="a", audience="promotion:X", approves=["accept"], role="reviewer",
    )


def test_grouped_mode_refuses_approves_chooses_from_and_excludes():
    with pytest.raises(ValidationError, match="NOT implemented"):
        HumanAwaitStep(
            kind="human_await", id="a", audience="promotion:X", approves=["accept"],
            role="reviewer", completion=CompletionPolicy(mode="grouped"),
        )
    with pytest.raises(ValidationError, match="NOT implemented"):
        HumanAwaitStep(
            kind="human_await", id="a", audience="promotion:X", excludes=["user:1"],
            completion=CompletionPolicy(mode="grouped"),
        )


# ── SignalAwaitStep ──────────────────────────────────────────────────────────────────────────

def test_signal_await_reason_required_must_be_drawn_from_accepts():
    SignalAwaitStep(
        kind="signal_await", id="s", signal="ack", audience="svc:x",
        accepts=["ok", "failed"], reason_required=["failed"],
    )
    with pytest.raises(ValidationError, match="is not in accepts"):
        SignalAwaitStep(
            kind="signal_await", id="s", signal="ack", audience="svc:x",
            accepts=["ok"], reason_required=["failed"],
        )


def test_signal_await_signal_name_must_match_the_lowercase_pattern():
    with pytest.raises(ValidationError):
        SignalAwaitStep(
            kind="signal_await", id="s", signal="Not-Valid", audience="svc:x", accepts=["ok"],
        )


# ── other step kinds — required-field and shape seals ───────────────────────────────────────

def test_spo_operation_requires_subject_and_verb():
    SpoOperationStep(kind="spo_operation", id="op", subject="inst:1", verb="verb:approve")
    with pytest.raises(ValidationError, match="subject='' — required"):
        SpoOperationStep(kind="spo_operation", id="op", subject="", verb="verb:approve")


def test_direct_call_capability_is_required_and_cannot_be_blank():
    with pytest.raises(ValidationError):
        DirectCallStep(kind="direct_call", id="dc", endpoint="https://x", capability="")


def test_dispatch_fanout_capability_is_required_and_cannot_be_blank():
    with pytest.raises(ValidationError):
        DispatchFanoutStep(kind="dispatch_fanout", id="df", capability="")


def test_wait_seconds_must_be_positive():
    WaitStep(kind="wait", id="w", seconds=1)
    with pytest.raises(ValidationError):
        WaitStep(kind="wait", id="w", seconds=0)


def test_emit_channel_must_match_the_lowercase_pattern():
    EmitStep(kind="emit", id="e", channel="outbox_a", template="hi")
    with pytest.raises(ValidationError):
        EmitStep(kind="emit", id="e", channel="Outbox", template="hi")


def test_render_step_accepts_any_template_shape():
    RenderStep(kind="render", id="r", template={"a": [1, 2, {"b": "c"}]})


def test_a_step_rejects_an_unknown_field():
    with pytest.raises(ValidationError):
        WaitStep(kind="wait", id="w", seconds=1, unexpected="surprise")


# ── load_workflow_definition ─────────────────────────────────────────────────────────────────

def test_load_workflow_definition_round_trips_a_yaml_file(tmp_path):
    p = tmp_path / "safety-check.yaml"
    p.write_text(
        "id: safety-check\nname: Safety Check\nsteps:\n"
        "  - kind: wait\n    id: settle\n    seconds: 60\n",
        encoding="utf-8",
    )
    d = load_workflow_definition(p)
    assert d.id == "safety-check"
    assert d.steps[0].kind == "wait"


def test_load_workflow_definition_wraps_a_parse_failure(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("id: [unterminated\n", encoding="utf-8")
    with pytest.raises(WorkflowDefinitionError, match="cannot read/parse"):
        load_workflow_definition(p)


def test_load_workflow_definition_rejects_a_non_mapping_top_level(tmp_path):
    p = tmp_path / "list.yaml"
    p.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(WorkflowDefinitionError, match="top level must be a mapping"):
        load_workflow_definition(p)


def test_load_workflow_definition_wraps_a_validation_failure(tmp_path):
    p = tmp_path / "invalid.yaml"
    p.write_text("id: ''\nname: D\nsteps: []\n", encoding="utf-8")
    with pytest.raises(WorkflowDefinitionError, match="invalid workflow definition"):
        load_workflow_definition(p)
