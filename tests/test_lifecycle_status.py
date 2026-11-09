"""`LifecycleStatus` / `LtbDecision` (ADR-0065 section D) / `ImpactRow` (ADR-0065 section 4,
ruled 2026-11-07). See `iagent_mesh/lifecycle_status.py`'s module docstring for the absent/null
distinction and for why `ImpactRow` is NOT a rename of `LtbDecision` — they are separate shapes
from separate sections.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from iagent_mesh.lifecycle_status import (
    DataProvenance,
    ImpactRow,
    LifecycleStatus,
    LifecycleStatusError,
    LtbDecision,
    UnknownLifecycleStatus,
    load_lifecycle_status_vocabulary,
    validate_status_known,
)


def test_lifecycle_status_requires_source_and_as_of():
    with pytest.raises(ValidationError):
        LifecycleStatus(status="active")  # missing source, as_of


def test_lifecycle_status_status_none_means_assessed_none_known():
    status = LifecycleStatus(status=None, source="board", as_of="2026-11-06T00:00:00Z")
    assert status.status is None
    assert status.source == "board"


def test_lifecycle_status_status_carries_an_open_vocabulary_string():
    status = LifecycleStatus(
        status="not-recommended-for-new-design", source="catalog", as_of="2026-11-06T00:00:00Z",
    )
    assert status.status == "not-recommended-for-new-design"


def test_lifecycle_status_successor_defaults_to_none():
    status = LifecycleStatus(status="obsolete", source="board", as_of="2026-11-06T00:00:00Z")
    assert status.successor is None
    status = LifecycleStatus(
        status="obsolete", source="board", as_of="2026-11-06T00:00:00Z", successor="part-2",
    )
    assert status.successor == "part-2"


def test_lifecycle_status_is_frozen_and_forbids_unknown_fields():
    status = LifecycleStatus(status="active", source="board", as_of="2026-11-06T00:00:00Z")
    with pytest.raises(ValidationError):
        status.status = "obsolete"
    with pytest.raises(ValidationError):
        LifecycleStatus(
            status="active", source="board", as_of="2026-11-06T00:00:00Z", extra_field="x",
        )


def test_ltb_decision_mirrors_section_d_fields():
    row = LtbDecision(quantity=50, by="svc:disposition-writer", rationale="PCN-1234", approved_by="role:engineering")
    assert row.quantity == 50
    assert row.by == "svc:disposition-writer"
    assert row.rationale == "PCN-1234"
    assert row.approved_by == "role:engineering"


def test_ltb_decision_requires_all_four_fields():
    with pytest.raises(ValidationError):
        LtbDecision(quantity=50, by="svc:x", rationale="PCN-1")  # missing approved_by


def test_ltb_decision_is_frozen_and_forbids_unknown_fields():
    row = LtbDecision(quantity=1, by="svc:x", rationale="r", approved_by="role:y")
    with pytest.raises(ValidationError):
        row.quantity = 2
    with pytest.raises(ValidationError):
        LtbDecision(quantity=1, by="svc:x", rationale="r", approved_by="role:y", extra_field="x")


def _impact_row(**overrides):
    fields = dict(
        end_item="end-item:f-35",
        program="program:alpha",
        component="part:1234",
        qty_per=4,
        as_of="2026-11-07T00:00:00Z",
        data_provenance=DataProvenance(
            dataset_urn="urn:dataset:bom-rollup", as_of="2026-11-07T00:00:00Z", ticket_id="T-1",
        ),
    )
    fields.update(overrides)
    return ImpactRow(**fields)


def test_impact_row_requires_its_identity_and_quantity_fields():
    row = _impact_row()
    assert row.end_item == "end-item:f-35"
    assert row.program == "program:alpha"
    assert row.component == "part:1234"
    assert row.qty_per == 4
    with pytest.raises(ValidationError):
        ImpactRow(
            program="program:alpha", component="part:1234", qty_per=4,
            as_of="2026-11-07T00:00:00Z",
            data_provenance=DataProvenance(
                dataset_urn="urn:x", as_of="2026-11-07T00:00:00Z", ticket_id="T-1",
            ),
        )  # missing end_item


def test_impact_row_population_and_stock_absent_is_not_zero():
    row = _impact_row()
    assert row.population is None
    assert row.stock is None
    row = _impact_row(population=0, stock=0)
    assert row.population == 0
    assert row.stock == 0


def test_impact_row_configuration_defaults_to_as_designed():
    row = _impact_row()
    assert row.configuration == "as_designed"
    row = _impact_row(configuration="as_built")
    assert row.configuration == "as_built"


def test_impact_row_data_provenance_carries_urn_as_of_and_ticket_id():
    row = _impact_row()
    assert row.data_provenance.dataset_urn == "urn:dataset:bom-rollup"
    assert row.data_provenance.ticket_id == "T-1"


def test_impact_row_is_frozen_and_forbids_unknown_fields():
    row = _impact_row()
    with pytest.raises(ValidationError):
        row.qty_per = 5
    with pytest.raises(ValidationError):
        _impact_row(extra_field="x")


def test_load_lifecycle_status_vocabulary_from_a_file(tmp_path: Path):
    p = tmp_path / "lifecycle_status.yaml"
    p.write_text(
        yaml.safe_dump({"statuses": ["active", "last-time-buy", "obsolete"]}), encoding="utf-8",
    )
    assert load_lifecycle_status_vocabulary(p) == ("active", "last-time-buy", "obsolete")


def test_load_lifecycle_status_vocabulary_refuses_an_empty_file(tmp_path: Path):
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(LifecycleStatusError):
        load_lifecycle_status_vocabulary(p)


def test_load_lifecycle_status_vocabulary_refuses_a_missing_statuses_key(tmp_path: Path):
    p = tmp_path / "broken.yaml"
    p.write_text(yaml.safe_dump({"other": ["active"]}), encoding="utf-8")
    with pytest.raises(LifecycleStatusError):
        load_lifecycle_status_vocabulary(p)


def test_load_lifecycle_status_vocabulary_refuses_a_blank_entry(tmp_path: Path):
    p = tmp_path / "blank.yaml"
    p.write_text(yaml.safe_dump({"statuses": ["active", ""]}), encoding="utf-8")
    with pytest.raises(LifecycleStatusError):
        load_lifecycle_status_vocabulary(p)


def test_validate_status_known_accepts_a_member_and_refuses_a_stranger():
    vocabulary = ("active", "last-time-buy", "obsolete")
    validate_status_known("active", vocabulary)  # does not raise
    with pytest.raises(UnknownLifecycleStatus):
        validate_status_known("retired-typo", vocabulary)


def test_validate_status_known_never_checks_none():
    validate_status_known(None, ())  # "assessed, none known" -- never a membership question
