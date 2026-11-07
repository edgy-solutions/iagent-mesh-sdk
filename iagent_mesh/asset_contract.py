"""``AssetContract`` — the Pydantic mirror of a ``contracts/<name>.yaml`` file (ADR-0066,
provisional number): what a governed read refuses on, stated as a row a deployment supplies
rather than as prose in a packet or constants hand-copied into a reader.

Mirrors the field shape of ``invincible-agent``'s ``contracts/ev_fixture.yaml`` (PR #275,
``0ee3c873``, 2026-11-05), named by the architect's directive as the first concrete instance —
"the first contract as data". That file's own header: "A SAMPLE, NOT A CUSTOMER'S SHAPE... a
deployment's own contract is its own file; nothing in engine code names this one." This module
ships the type and the loader; it never ships a customer's contract.

``dag-tools`` imports this module to validate a materialized asset's schema against the contract
a deployment supplies for it, per the directive ("dag-tools imports it").

── WHAT ``validate`` CHECKS, AND WHAT IT DOES NOT ──────────────────────────────────────────────
``ev_fixture.yaml``'s ``rules`` names eleven refusals. Most are row/value-level
(``null_value``, ``non_finite``, uniqueness, duplication, ``varies_within_path``) and need the
materialized data to check — this module never materializes a read (see :class:`DataRef` for why:
dag-tools imports this SDK, this SDK does not import dag-tools or a dataframe library). Only two
are checkable from a schema alone, so :func:`validate` checks only those: ``missing_column`` (a
required column absent) and ``wrong_type`` (a declared column present under a different type).
The row/value-level rules stay the reader's own job, same division :class:`DataRef` already draws
between declaring a read and performing one.

``dataframe_schema`` takes the same shape as :attr:`DataRef.schema_` — a plain tuple of
``(name, type_name)`` pairs — deliberately, so a caller already holding a resolved ``DataRef``
passes its ``schema_`` straight through. ``type_name`` is compared against the contract column's
own ``type`` string (``"string"``/``"numeric"``/``"integer"`` in ``ev_fixture.yaml``, open per
generic-at-birth) by exact match: normalizing a substrate's own type names (polars ``Utf8``,
pyarrow ``int64``, ...) into that vocabulary is the caller's job, not this module's — the same
one-way dependency reasoning that keeps this file free of a dataframe library.

``AssetContractColumn.level`` and ``AssetContractDataset.max_level`` (v0.9.16, per
invincible-agent's gov-to-ca packet of 2026-11-06, itself per the architect's ruling 4 on
``invincible-agent#276``) carry ADR-0064's per-column/per-dataset classification. Both are open
strings against ``policy/classification/dimensions.yaml``'s vocabulary — this module ships
neither the vocabulary nor the ordering check; gov's own validator holds both, per that packet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from .declarations import DeclarationError, load_rows

__all__ = [
    "AssetContractDataset",
    "AssetContractPeriod",
    "AssetContractColumn",
    "AssetContractLimits",
    "AssetContractCadence",
    "AssetContract",
    "AssetContractError",
    "load_asset_contract",
    "load_asset_contracts",
    "validate",
]


class AssetContractError(DeclarationError):
    """A ``contracts/<name>.yaml`` row is invalid; see ``DeclarationError``. A family subclass
    (same pattern as ``ExportProfileError``/``task_kinds.TaskKindError``) so a caller can catch
    contract-loading failures specifically."""


class AssetContractDataset(BaseModel):
    """``dataset`` — derived facts about the asset this contract governs, never typed ahead of
    materialization (``ev_fixture.yaml``'s own comment: "DERIVED, never typed: materialize, then
    read what the broker registered or the catalog shows")."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    urn: str
    producer: dict[str, str]
    """``{repo, asset}`` — where this asset is produced."""
    storage: str
    """E.g. ``"file"`` or a table-backed storage kind. Open string, not ``Literal``: a new storage
    kind is a deployment's row, not an SDK release."""
    banner: Optional[str] = None
    """A human-readable caution, e.g. marking a synthetic fixture. ``None`` means none declared."""
    max_level: Optional[str] = None
    """The dataset's ceiling on the classification hierarchy (ADR-0064), drawn from
    ``policy/classification/dimensions.yaml``'s one ``hierarchical`` dimension -- an open string,
    not ``Literal``/``Enum``: the vocabulary is the deployment's. ``None`` means unlabelled; under
    ADR-0064 an unlabelled source is the most restrictive, but that ordering lives in the
    consumer's own validator (gov's), not here -- this module does not import the vocabulary to
    order against it."""


class AssetContractPeriod(BaseModel):
    """``period`` — which column carries the reporting period and which vocabulary it is drawn
    from (the reader's own closed enum, e.g. ``FISCAL_PERIODS``; this module does not import or
    validate against it — a value-level check, out of :func:`validate`'s schema-level scope)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str
    vocabulary: str


class AssetContractColumn(BaseModel):
    """One declared column. ``required``: every governed read selects it. ``produced_since``:
    the producer's release that first carries it; ``None`` means declared but not yet produced —
    a reader naming it gets ``missing_column`` until it is. ``constant_within``: the columns
    inside which every row carries one value. ``additive_over``: the axes along which summing the
    column is meaningful."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    type: str
    """E.g. ``"string"``, ``"numeric"``, ``"integer"``. Open string, not ``Literal``/``Enum``: a
    new column type is a deployment's row, not an SDK release, per generic-at-birth."""
    unit: Optional[str] = None
    required: bool = False
    produced_since: Optional[str] = None
    constant_within: tuple[str, ...] = ()
    additive_over: tuple[str, ...] = ()
    level: Optional[str] = None
    """This column's place on the classification hierarchy (ADR-0064), same vocabulary and same
    ``None``-is-unlabelled-and-most-restrictive posture as :attr:`AssetContractDataset.max_level`
    -- see that attribute's docstring."""


class AssetContractLimits(BaseModel):
    """``limits`` — the row cap a read is refused above, named by an env var and a default so a
    reader's own constants and the contract can be checked against each other (the pattern
    ``test_the_ev_contract_agrees_with_the_reader.py`` pins)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_rows: dict[str, Any]
    """``{env, default}``."""


class AssetContractCadence(BaseModel):
    """``cadence`` — who sets freshness and how a producer writes (e.g. ``whole_table``, so a
    partial rewrite that leaves a stale part file is a known risk a reader can refuse on, not
    this module's job to detect)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    set_by: str
    write: str


class AssetContract(BaseModel):
    """The Pydantic mirror of a ``contracts/<name>.yaml`` file. See the module docstring for the
    authoritative instance this mirrors field-for-field (``ev_fixture.yaml``) and for what
    :func:`validate` checks against it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    version: str
    status: str
    """E.g. ``"sample"``, ``"proposed"``, ``"ratified"``. Open string, not ``Literal``: a
    deployment's own ratification vocabulary, not this SDK's to enumerate."""
    ratified_by: str
    """A seat (e.g. ``"owner"``), not a person — same convention :data:`GRANTED_BY_SEED` and the
    architect's 2026-10-31 ``ratified_by`` ruling already carry elsewhere in this SDK."""

    dataset: AssetContractDataset
    grain: tuple[str, ...]
    """The column tuple forming one row's key, e.g. ``("work_package", "period")``."""
    scope: str
    """The column a read filters to one value of."""
    period: AssetContractPeriod
    status_period: Optional[str] = None
    """Names which column marks the reporting period a time-phased row draws from data, so it is
    never a constant in a measure row. ``None`` means the contract declares no such column."""

    columns: tuple[AssetContractColumn, ...] = ()
    rules: dict[str, str] = {}
    """Rule id → human description, naming every refusal the reader can raise."""
    limits: Optional[AssetContractLimits] = None
    cadence: Optional[AssetContractCadence] = None
    tags: dict[str, Any] = {}


def _asset_contract_row(raw: dict) -> AssetContract:
    return AssetContract.model_validate(raw)


def load_asset_contract(path: Path | str) -> AssetContract:
    """Load one ``contracts/<name>.yaml`` file by path."""
    import yaml

    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if raw is None:
        raise AssetContractError(f"{p.name} is empty — an empty asset contract is not a contract")
    try:
        return AssetContract.model_validate(raw)
    except AssetContractError:
        raise
    except Exception as exc:  # noqa: BLE001 — re-raised with the file named
        raise AssetContractError(f"{p.name} is not a valid asset contract: {exc}") from exc


def load_asset_contracts(directory: Path | str) -> dict[str, AssetContract]:
    """Every asset contract in one directory, validated, keyed by ``contract_id``.

    Built on :func:`iagent_mesh.declarations.load_rows` — a contract file is a ratified row
    (``status`` carries the same ``sample``/``proposed``/``ratified`` life cycle ``load_rows``'s
    own family of callers already uses), not a seed-plus-overlay composed set: nothing in either
    the architect's directive or ``ev_fixture.yaml``'s own packet names an overlay mechanism for
    contracts, so this does not reach for :func:`iagent_mesh.declarations.compose_rows`."""
    rows = load_rows(
        directory,
        key_field="contract_id",
        builder=_asset_contract_row,
        label="asset contract",
        error=AssetContractError,
    )
    return {row.contract_id: row for row in rows}


def validate(
    dataframe_schema: tuple[tuple[str, str], ...],
    contract: AssetContract,
) -> tuple[dict[str, str], ...]:
    """The schema-level subset of ``contract.rules`` checkable without materializing the read:
    ``missing_column`` (a required column absent from ``dataframe_schema``) and ``wrong_type`` (a
    present column's ``type_name`` does not match the contract's declared ``type``). See the
    module docstring for why the remaining, row/value-level rules are out of scope here.

    Returns every violation found, not just the first — a caller refusing a read wants to name
    every broken column at once, not re-run this after fixing one."""
    present = dict(dataframe_schema)
    violations: list[dict[str, str]] = []
    for column in contract.columns:
        if column.name not in present:
            if column.required:
                violations.append({"rule": "missing_column", "column": column.name})
            continue
        if present[column.name] != column.type:
            violations.append({"rule": "wrong_type", "column": column.name})
    return tuple(violations)
