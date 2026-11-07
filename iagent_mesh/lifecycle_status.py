"""``LifecycleStatus`` / ``LtbDecision`` / ``ImpactRow`` — three row shapes for the
``obsolescence_resolution`` workflow, split across two ADR-0065 sections (provisional number; the
ADR itself is not yet a committed file anywhere, confirmed absent from
``invincible-agent/docs/adr/`` as of 2026-11-06).

``LifecycleStatus`` and ``LtbDecision`` are section D's own two field kinds, recovered verbatim
from a ``doc-tools`` packet (commit ``dfc90d7``) since the ADR text itself is not reachable in
this repo's sibling:

    field kinds ``lifecycle_status {status, source, as_of, successor?}`` and
    ``ltb_decision {quantity, by, rationale, approved_by}``; workflow
    ``obsolescence_resolution`` as already written.

Both ship unchanged — ``LifecycleStatus`` mirrors ``lifecycle_status`` with no rename (the name
is already generic), and ``LtbDecision`` mirrors ``ltb_decision`` the same way. An earlier draft
of this module renamed ``ltb_decision`` to ``ImpactRow`` on the theory that naming a type after
one disposition (last-time-buy) violated generic-at-birth; the architect's 2026-11-06 correction
(via Chris) ruled that reading wrong — ``LtbDecision`` is section D's own shape, under its own
name, and ``ImpactRow`` is a *different* type entirely, from a *different* section:

``ImpactRow`` is "the where-used impact-table row," ADR-0065 **section E** — a distinct shape
from section D's two field kinds, per the same correction. Section E has no committed text
anywhere either; a search of ``invincible-agent`` (board items, ``sessions/*.md``) and
``doc-tools`` (git history, working tree, including a grep for where-used/cross-reference-shaped
field names) found zero field-level spec — only confirmation that "where-used" IS section E
(lane 01's 2026-11-06 reassignment-table packet: *"where-used (ADR directive item E) has no item
yet... I'd send it to 74..."*). **The three fields below are this module's own judgment call, not
a recovered spec** — the minimal shape a where-used/impact row cannot do its job without: which
part, where it is used, how many. Same discipline as the earlier (wrong) call: flagged explicitly
to the architect via Chris, cheap to reshape now since nothing downstream imports this module yet.

── THE ABSENT/NULL DISTINCTION (section D's one detail worth not losing) ──────────────────────
"status absent = not assessed, status null = assessed, none known." This is two levels, not one:

* Whatever record CARRIES a ``lifecycle_status`` field as ``Optional[LifecycleStatus] = None``
  decides "not assessed" at that outer level — the field is absent/``None`` because no assessment
  ever ran. This module does not define that outer record; the emitter does (lane 1's disposition
  writer, per the architect's 2026-11-06 reassignment — doc-tools declares nothing here).
* Once a :class:`LifecycleStatus` IS present, its own ``status`` being ``None`` means "assessed,
  but no determination reached" — a positive fact, not an absence. A reader must not conflate the
  two levels: a present ``LifecycleStatus(status=None, ...)`` is not the same claim as no
  ``LifecycleStatus`` at all.

This module ships the row shapes only — not the emitter, the registry, or the
``obsolescence_resolution`` workflow runner, the same division every other row-shape module in
this SDK draws (:mod:`iagent_mesh.maintenance_bridge`, :mod:`iagent_mesh.asset_contract`).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

__all__ = [
    "LifecycleStatus",
    "LtbDecision",
    "ImpactRow",
]


class LifecycleStatus(BaseModel):
    """``lifecycle_status {status, source, as_of, successor?}`` — ADR-0065 section D, unchanged.
    See the module docstring for the absent-vs-null distinction this field kind exists to carry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Optional[str] = None
    """An open string against a deployment's own ``policy/registry/lifecycle_status.yaml`` —
    never an enum here, per generic-at-birth. ``None`` means assessed, none known (see module
    docstring); it is a positive fact, not an absence — the absence case is one level up, on
    whatever record carries this field at all."""
    source: str
    """Who or what produced this assessment, e.g. a board or a catalog feed."""
    as_of: str
    """ISO-8601, this SDK's house convention for a wire timestamp — never ``datetime``."""
    successor: Optional[str] = None
    """Names a successor part when ``status`` is e.g. obsolete. ``None`` means none declared."""


class LtbDecision(BaseModel):
    """``ltb_decision {quantity, by, rationale, approved_by}`` — ADR-0065 section D, unchanged.
    The decided impact-mitigation for whichever disposition option a workflow's decide step
    actually resolved to (last-time-buy is one such option, not the only one — see the module
    docstring; the type keeps section D's own name per the architect's 2026-11-06 correction)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: int
    """How many units the decision covers."""
    by: str
    """Who made the decision."""
    rationale: str
    approved_by: str
    """The approving seat, distinct from ``by`` the deciding one — same chain-entry posture
    :class:`iagent_mesh.maintenance_bridge.ApprovalChainEntry` already carries elsewhere in this
    SDK."""


class ImpactRow(BaseModel):
    """The where-used impact-table row, ADR-0065 section E. No field-level spec for section E
    exists anywhere this module's docstring could cite — these three fields are this module's own
    minimal, explicitly-flagged judgment call (see module docstring): which part is being assessed
    for obsolescence impact, where it is used, and how many units that use consumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    part_ref: str
    """The part/asset being surveyed for obsolescence impact."""
    used_by: str
    """The consuming program/assembly/product, named generically per generic-at-birth — never a
    specific program name in code. One row per (``part_ref``, ``used_by``) pair; a part used by
    three programs is three rows, not one row with a list."""
    quantity: Optional[int] = None
    """Quantity-per-``used_by``. ``None`` when the survey has not yet quantified this usage —
    distinct from ``0``, which would claim a quantified-zero usage."""
