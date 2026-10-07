"""Seals for the 0.9.8 maintenance bridge wire shapes — `MaintenanceEvent`/`ActionRecord`/
`ApprovalChainEntry`, mirroring ADR-0046 §1/§4 per the week-1 contract packet. One seal per
ruling the module docstring states, so a later edit that quietly reverses a ruling fails here
first.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.maintenance_bridge import (
    ActionProvenance,
    ActionRecord,
    ApprovalChainEntry,
    BattleCondition,
    BattleConditionBasis,
    EventProvenanceRow,
    EventSource,
    Fault,
    MaintenanceEvent,
    PartRow,
    Picture,
    ReleasabilityLabel,
    SpareRow,
    TaskRef,
    WorkOrder,
)


def _label() -> ReleasabilityLabel:
    return ReleasabilityLabel(originator_nation="USA", releasable_to=("USA", "GBR"))


def _spare_row(site="site-a", on_hand=2, lead_time_days=5, lead_time_source="supply-system"
              ) -> SpareRow:
    return SpareRow(site=site, on_hand=on_hand, as_of="2026-10-04T00:00:00Z",
                    lead_time_days=lead_time_days, lead_time_source=lead_time_source)


def _picture(nearest_spare=None) -> Picture:
    return Picture(
        readiness="FMC", factors=("no stock",), lifecycle="in-service",
        spares=(_spare_row(),), nearest_spare=nearest_spare,
        battle_condition=BattleCondition(
            mission_essential=True,
            basis=BattleConditionBasis(rule="rule-1", observed_at="2026-10-04T00:00:00Z"),
        ),
    )


def _event(**overrides) -> MaintenanceEvent:
    fields = dict(
        event_id="evt-1", kind="cm_discrepancy", asset_id="asset-1", owning_tier="tier-1",
        fault=Fault(item="array module", fault_code="FC-1", observed_at="2026-10-04T00:00:00Z"),
        sources=(EventSource(source="maintainer_report", reported_by="sub-1",
                             observed_at="2026-10-04T00:00:00Z", row_ref="row-1"),),
        picture=_picture(), label=_label(), provenance=(
            EventProvenanceRow(row_key="row-1", observed_at="2026-10-04T00:00:00Z"),
        ),
    )
    fields.update(overrides)
    return MaintenanceEvent(**fields)


def _part_row(**overrides) -> PartRow:
    fields = dict(item="part-1", part_ref="ref-1", quantity=1)
    fields.update(overrides)
    return PartRow(**fields)


def _approval_entry(**overrides) -> ApprovalChainEntry:
    fields = dict(step=1, role="role-1", approver_sub="sub-1", decision="approved",
                 decided_at="2026-10-04T00:00:00Z", decision_record_ref="dr-1")
    fields.update(overrides)
    return ApprovalChainEntry(**fields)


def _action(**overrides) -> ActionRecord:
    fields = dict(
        action_id="act-1", event_id="evt-1", asset_id="asset-1", owning_tier="tier-1",
        label=_label(),
        work_order=WorkOrder(task="remove and replace", task_refs=(
            TaskRef(graph_uri="graph://node-1", data_module_code="DMC-1"),
        ), parts=(_part_row(),), outcome="approved"),
        approval_chain=(_approval_entry(),),
        provenance=ActionProvenance(
            workflow_definition_id="wf-def-1", workflow_definition_version="1",
            workflow_instance_id="wf-inst-1", manual_nodes_consulted=("graph://node-1",),
        ),
    )
    fields.update(overrides)
    return ActionRecord(**fields)


# ── MaintenanceEvent ─────────────────────────────────────────────────────────────────────

def test_maintenance_event_constructs_from_the_full_packet_shape():
    event = _event()
    assert event.fault.item == "array module"
    assert event.picture.nearest_spare is None


def test_maintenance_event_sources_must_be_nonempty():
    with pytest.raises(ValidationError, match="not an episode"):
        _event(sources=())


def test_maintenance_event_is_frozen():
    event = _event()
    with pytest.raises(ValidationError):
        event.asset_id = "asset-2"  # type: ignore[misc]


def test_maintenance_event_rejects_an_unknown_kind():
    with pytest.raises(ValidationError):
        _event(kind="not_a_kind")


def test_maintenance_event_rejects_extra_fields():
    with pytest.raises(ValidationError):
        MaintenanceEvent(**{**_event().model_dump(), "extra_field": "x"})


# ── Picture.nearest_spare: None is a business value, not an absent fact ────────────────────

def test_nearest_spare_defaults_to_none_meaning_no_stock_anywhere():
    picture = _picture()
    assert picture.nearest_spare is None


def test_nearest_spare_carries_the_same_shape_as_a_spares_row():
    nearest = _spare_row(site="site-b", on_hand=1)
    picture = _picture(nearest_spare=nearest)
    assert picture.nearest_spare.site == "site-b"


# ── SpareRow / lead_time_source vocabulary ──────────────────────────────────────────────

def test_spare_row_lead_time_source_is_closed_to_the_ruled_vocabulary():
    with pytest.raises(ValidationError):
        _spare_row(lead_time_source="overnight-courier")


def test_spare_row_quantities_cannot_be_negative():
    with pytest.raises(ValidationError, match="cannot be negative"):
        _spare_row(on_hand=-1)


# ── PartRow: source_site optional (0.9.8), four additive nullable fields ───────────────────

def test_part_row_source_site_defaults_to_none():
    row = _part_row()
    assert row.source_site is None


def test_part_row_additive_fields_default_to_none():
    row = _part_row()
    assert row.icn is None
    assert row.hotspot_id is None
    assert row.lead_time_days is None
    assert row.lead_time_source is None


def test_part_row_lead_time_fields_may_both_be_set():
    row = _part_row(lead_time_days=3, lead_time_source="stand-in")
    assert row.lead_time_days == 3
    assert row.lead_time_source == "stand-in"


def test_part_row_lead_time_days_without_source_is_refused():
    with pytest.raises(ValidationError, match="set together or not at all"):
        _part_row(lead_time_days=3)


def test_part_row_lead_time_source_without_days_is_refused():
    with pytest.raises(ValidationError, match="set together or not at all"):
        _part_row(lead_time_source="stand-in")


def test_part_row_quantity_must_be_positive():
    with pytest.raises(ValidationError, match="zero or fewer"):
        _part_row(quantity=0)


# ── WorkOrder.outcome: final values only ────────────────────────────────────────────────

def test_work_order_outcome_is_closed_to_approved_or_rejected():
    with pytest.raises(ValidationError):
        WorkOrder(task="t", task_refs=(), parts=(), outcome="pending")


# ── ApprovalChainEntry: does not itself check approver_sub resolution ──────────────────────

def test_approval_chain_entry_accepts_any_opaque_approver_sub():
    entry = _approval_entry(approver_sub="not-a-known-approver")
    assert entry.approver_sub == "not-a-known-approver"


def test_approval_chain_entry_decision_is_closed_to_final_values():
    with pytest.raises(ValidationError):
        _approval_entry(decision="pending")


def test_approval_chain_entry_step_cannot_be_negative():
    with pytest.raises(ValidationError, match="cannot be negative"):
        _approval_entry(step=-1)


# ── ActionRecord ─────────────────────────────────────────────────────────────────────────

def test_action_record_constructs_from_the_full_packet_shape():
    action = _action()
    assert action.work_order.outcome == "approved"
    assert action.approval_chain[0].step == 1


def test_action_record_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ActionRecord(**{**_action().model_dump(exclude={"label", "work_order", "approval_chain",
                                                         "provenance"}),
                       "label": _label(), "work_order": _action().work_order,
                       "approval_chain": _action().approval_chain,
                       "provenance": _action().provenance, "extra_field": "x"})


def test_action_record_label_is_the_same_shape_as_the_event_label():
    event = _event()
    action = _action(label=event.label)
    assert action.label == event.label


# ── blank required strings ──────────────────────────────────────────────────────────────

def test_blank_required_strings_refused():
    with pytest.raises(ValidationError):
        _event(event_id="")
    with pytest.raises(ValidationError):
        _action(action_id="")
    with pytest.raises(ValidationError):
        _part_row(item="")
    with pytest.raises(ValidationError):
        _approval_entry(role="")
