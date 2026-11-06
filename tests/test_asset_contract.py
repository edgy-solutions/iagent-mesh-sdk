"""`AssetContract` mirrors `contracts/ev_fixture.yaml` (invincible-agent PR #275, `0ee3c873`,
2026-11-05) field-for-field — the first contract as data (ADR-0066, provisional). The literal
YAML below is a verbatim copy of that committed file (minus its header comments, which carry no
fields), not a paraphrase, so `test_the_real_ev_fixture_contract_loads_field_for_field` is a
fidelity check against the actual artifact dag-tools and engine-fin agreed on, not against this
module's own idea of its shape.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from iagent_mesh.asset_contract import (
    AssetContract,
    AssetContractError,
    load_asset_contract,
    load_asset_contracts,
    validate,
)

EV_FIXTURE_CONTRACT = """
contract_id: ev_fixture
version: "1.0.0"
status: sample
ratified_by: owner

dataset:
  urn: "urn:li:dataset:(urn:li:dataPlatform:s3,ev_fixture,PROD)"
  producer: {repo: dag-tools, asset: ev_fixture}
  storage: file
  banner: "SYNTHETIC earned-value fixture, not a real program."

grain: [work_package, period]
scope: program_id

period:
  column: period
  vocabulary: FISCAL_PERIODS
status_period: status_period

columns:
  - {name: program_id, type: string, required: true, produced_since: "0.11.0"}
  - {name: program_name, type: string, required: true, produced_since: "0.11.0",
     constant_within: [program_id]}
  - {name: program_bac, type: numeric, unit: USD, required: true, produced_since: "0.11.0",
     constant_within: [program_id], additive_over: []}
  - {name: control_account, type: string, required: true, produced_since: "0.11.0",
     constant_within: [work_package]}
  - {name: work_package, type: string, required: true, produced_since: "0.11.0"}
  - {name: period, type: string, required: true, produced_since: "0.11.0"}
  - {name: bcws, type: numeric, unit: USD, required: true, produced_since: "0.11.0",
     additive_over: [work_package, period]}
  - {name: bcwp, type: numeric, unit: USD, required: true, produced_since: "0.11.0",
     additive_over: [work_package, period]}
  - {name: acwp, type: numeric, unit: USD, required: true, produced_since: "0.11.0",
     additive_over: [work_package, period]}
  - {name: bac, type: integer, unit: USD, required: false, produced_since: "0.11.0",
     constant_within: [work_package], additive_over: [work_package]}
  - {name: eac, type: integer, unit: USD, required: false, produced_since: "0.11.0",
     constant_within: [work_package], additive_over: [work_package]}
  - {name: status_period, type: string, required: false, produced_since: null,
     constant_within: [program_id]}
  - {name: eac_reported, type: integer, unit: USD, required: false, produced_since: null,
     additive_over: [work_package]}

rules:
  missing_column: "a required column, or a column a measure row names, is absent"
  wrong_type: "a string column is not a string, or a numeric column is not numeric"
  null_value: "a null in a column that is read"
  non_finite: "a NaN or infinity in a numeric column that is read"
  other_program_rows: "a read holds rows of another program (the asset may; a read that kept them forgot its filter)"
  program_name_not_unique: "more than one program_name for the program"
  program_bac_not_unique: "program_bac differs between the program's rows"
  work_package_in_two_accounts: "a work_package appears under more than one control_account"
  duplicate_work_package_period: "more than one row for a (work_package, period)"
  period_outside_calendar: "a period outside the vocabulary"
  varies_within_path: "under `per_path: once`, a path's rows carry different amounts"

limits:
  max_rows: {env: FIN_ASSET_MAX_ROWS, default: 100000}

cadence:
  set_by: producer
  write: whole_table

tags:
  required: []
  datahub/urn: only_if_true
"""


def test_the_real_ev_fixture_contract_loads_field_for_field():
    raw = yaml.safe_load(EV_FIXTURE_CONTRACT)
    contract = AssetContract.model_validate(raw)

    assert contract.contract_id == "ev_fixture"
    assert contract.version == "1.0.0"
    assert contract.status == "sample"
    assert contract.ratified_by == "owner"

    assert contract.dataset.urn == "urn:li:dataset:(urn:li:dataPlatform:s3,ev_fixture,PROD)"
    assert contract.dataset.producer == {"repo": "dag-tools", "asset": "ev_fixture"}
    assert contract.dataset.storage == "file"

    assert contract.grain == ("work_package", "period")
    assert contract.scope == "program_id"
    assert contract.period.column == "period"
    assert contract.period.vocabulary == "FISCAL_PERIODS"
    assert contract.status_period == "status_period"

    by_name = {c.name: c for c in contract.columns}
    assert len(by_name) == 13
    assert by_name["program_id"].required is True
    assert by_name["program_bac"].unit == "USD"
    assert by_name["program_name"].constant_within == ("program_id",)
    assert by_name["bcws"].additive_over == ("work_package", "period")
    assert by_name["status_period"].produced_since is None
    assert by_name["eac_reported"].required is False

    assert set(contract.rules) == {
        "missing_column", "wrong_type", "null_value", "non_finite", "other_program_rows",
        "program_name_not_unique", "program_bac_not_unique", "work_package_in_two_accounts",
        "duplicate_work_package_period", "period_outside_calendar", "varies_within_path",
    }

    assert contract.limits.max_rows == {"env": "FIN_ASSET_MAX_ROWS", "default": 100000}
    assert contract.cadence.set_by == "producer"
    assert contract.cadence.write == "whole_table"
    assert contract.tags == {"required": [], "datahub/urn": "only_if_true"}


def test_an_unknown_top_level_field_is_refused():
    """`extra="forbid"` — a contract field this module has not mirrored is a gap to close, not a
    silently dropped fact, same discipline `DataRef`/`ExportProfileHeader` already hold."""
    raw = yaml.safe_load(EV_FIXTURE_CONTRACT)
    raw["a_field_this_module_does_not_know"] = "surprise"
    with pytest.raises(Exception):
        AssetContract.model_validate(raw)


def test_load_asset_contract_from_a_file(tmp_path: Path):
    p = tmp_path / "ev_fixture.yaml"
    p.write_text(EV_FIXTURE_CONTRACT, encoding="utf-8")

    contract = load_asset_contract(p)

    assert contract.contract_id == "ev_fixture"


def test_load_asset_contract_refuses_an_empty_file(tmp_path: Path):
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")

    with pytest.raises(AssetContractError):
        load_asset_contract(p)


def test_load_asset_contract_refuses_a_missing_required_field(tmp_path: Path):
    p = tmp_path / "broken.yaml"
    p.write_text('contract_id: broken\nversion: "1.0.0"\n', encoding="utf-8")

    with pytest.raises(AssetContractError):
        load_asset_contract(p)


def test_load_asset_contracts_keys_by_contract_id(tmp_path: Path):
    (tmp_path / "ev_fixture.yaml").write_text(EV_FIXTURE_CONTRACT, encoding="utf-8")
    other = yaml.safe_load(EV_FIXTURE_CONTRACT)
    other["contract_id"] = "another_asset"
    (tmp_path / "another.yaml").write_text(yaml.safe_dump(other), encoding="utf-8")

    contracts = load_asset_contracts(tmp_path)

    assert set(contracts) == {"ev_fixture", "another_asset"}
    assert contracts["ev_fixture"].contract_id == "ev_fixture"


def test_load_asset_contracts_refuses_two_files_sharing_a_contract_id(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(EV_FIXTURE_CONTRACT, encoding="utf-8")
    (tmp_path / "b.yaml").write_text(EV_FIXTURE_CONTRACT, encoding="utf-8")

    with pytest.raises(AssetContractError):
        load_asset_contracts(tmp_path)


@pytest.fixture
def ev_fixture_contract() -> AssetContract:
    return AssetContract.model_validate(yaml.safe_load(EV_FIXTURE_CONTRACT))


def test_validate_passes_a_schema_that_satisfies_every_required_column(ev_fixture_contract):
    schema = tuple(
        (c.name, c.type) for c in ev_fixture_contract.columns if c.required
    )
    assert validate(schema, ev_fixture_contract) == ()


def test_validate_reports_a_missing_required_column(ev_fixture_contract):
    schema = tuple(
        (c.name, c.type) for c in ev_fixture_contract.columns
        if c.required and c.name != "program_bac"
    )
    violations = validate(schema, ev_fixture_contract)
    assert {"rule": "missing_column", "column": "program_bac"} in violations


def test_validate_does_not_report_a_missing_optional_column(ev_fixture_contract):
    """`eac` is declared `required: false` — a schema that omits it is not a violation."""
    schema = tuple(
        (c.name, c.type) for c in ev_fixture_contract.columns
        if c.required and c.name != "eac"
    )
    violations = validate(schema, ev_fixture_contract)
    assert violations == ()


def test_validate_reports_a_wrong_type(ev_fixture_contract):
    schema = tuple(
        (c.name, "numeric" if c.name == "program_id" else c.type)
        for c in ev_fixture_contract.columns if c.required
    )
    violations = validate(schema, ev_fixture_contract)
    assert {"rule": "wrong_type", "column": "program_id"} in violations


def test_validate_reports_every_violation_not_just_the_first(ev_fixture_contract):
    schema = tuple(
        (c.name, "numeric" if c.name == "program_id" else c.type)
        for c in ev_fixture_contract.columns
        if c.required and c.name not in ("program_name",)
    )
    violations = validate(schema, ev_fixture_contract)
    assert {"rule": "wrong_type", "column": "program_id"} in violations
    assert {"rule": "missing_column", "column": "program_name"} in violations
    assert len(violations) == 2
