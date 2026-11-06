"""``MeasureSeries`` / ``MeasureSeriesReference`` — the first shared render-declaration model for
a MULTI_SERIES measure row (Fork A1, ruled 2026-11-05: ``invincible-agent``
``sessions/2026-11-05-packet-to-architect-cc-ca-dag-tools-cortex-from-fin-time-phasing-census-and-
three-premises-to-rule-before-the-rows.md``, lane/fin's time-phasing census).

Before this, the series declaration had two independently hand-rolled homes: fin's loader
(``measure_verbs.py``, ``render.series = [{key, label, unit?}]`` and
``render.target = {value, label}``) and cortex-ui's ``src/archetypes/multi-series/contract.ts``
(``series``, plus a constant-only ``reference = {value, label}``). Fork A1 is this SDK minting
the first shared class so both converge onto one shape instead of staying parity-sealed copies —
the same pattern :class:`iagent_mesh.interfaces.DataRef`/the MeshData Protocol already set for
fin's PR #219 hand-built resolver.

These are FIELDS on the existing MULTI_SERIES archetype, not a new archetype — Fork A1's own
wording, kept verbatim because the alternative (a new archetype) was explicitly rejected.

``cumulative`` states a FACT about the values a series already carries when served, never a cue
for a renderer to accumulate them itself — Fork A1's own caution, repeated here because a
renderer that treated it as an instruction would double-sum every series it draws.

``fin:DeclaredMeasureSeries`` (``measure_verbs.py:127``) is the ontology class every measure row
returns — a URI, not this Python type. This module's job ends at the declared shape; it does not
touch the ontology output.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

__all__ = [
    "MeasureSeries",
    "MeasureSeriesReference",
]


class MeasureSeries(BaseModel):
    """One declared series on a MULTI_SERIES row — ``{key, label, unit?, cumulative?}``, Fork
    A1's exact field list."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    """Identity other fields point at — a :class:`MeasureSeriesReference`'s own ``series`` names
    one of these by this field."""
    label: str
    unit: Optional[str] = None
    cumulative: bool = False
    """A fact about the values this series is served with (a running sum already computed by the
    producer, e.g. fin's pure cumulative module) — never an instruction for the renderer to
    accumulate them itself."""


class MeasureSeriesReference(BaseModel):
    """A reference line on a MULTI_SERIES row — ``{label}`` plus exactly one of ``value`` (a
    constant) or ``series`` (a declared :class:`MeasureSeries`'s ``key``), Fork A1's exact shape.
    Example from the census: ``{series: "bac", label: "BAC"}`` — BAC served from data rather than
    declared as a constant in the row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    value: Optional[float] = None
    series: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_of_value_or_series(self) -> "MeasureSeriesReference":
        if (self.value is None) == (self.series is None):
            raise ValueError(
                "MeasureSeriesReference must set exactly one of `value` or `series` — "
                f"got value={self.value!r}, series={self.series!r}"
            )
        return self
