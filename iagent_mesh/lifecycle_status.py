"""``LifecycleStatus`` / ``ImpactRow`` — the two field kinds ADR-0065 section D names (provisional
number; the ADR itself is not yet a committed file anywhere, confirmed absent from
``invincible-agent/docs/adr/`` as of 2026-11-06), recovered verbatim from a ``doc-tools`` packet
(commit ``dfc90d7``) since the ADR text itself is not reachable in this repo's sibling:

    field kinds ``lifecycle_status {status, source, as_of, successor?}`` and
    ``ltb_decision {quantity, by, rationale, approved_by}``; workflow
    ``obsolescence_resolution`` as already written.

**``ImpactRow`` renames section D's ``ltb_decision``, field-for-field, on purpose.**
``ltb_decision`` names one disposition (last-time-buy) in the type itself, which the standing
rule this SDK already follows for ``options``/``level`` refuses: "nothing in dag-tools or iagent
names a ... program, dimension or level in code" extends here to a disposition option. The
``obsolescence_resolution`` workflow's own disposition vocabulary (lived on a decide step's
``options``, see :class:`iagent_mesh.workflow_definition.HumanAwaitStep`) is already more than
last-time-buy alone — gov's own fork notes name a generic ``archive`` disposition sitting
alongside it. This module ships the generic shape (the decided impact-mitigation: how much, by
whom, why, approved by whom) so it applies to whichever option the decide step actually resolved
to, not only LTB. The field names themselves (``quantity``, ``by``, ``rationale``, ``approved_by``)
are section D's own, unchanged — only the type's name is genericized. If the architect's actual
intent for "ImpactRow" differs from this reading, it is cheap to rename; nothing downstream
depends on this module's name yet.

``LifecycleStatus`` mirrors ``lifecycle_status`` with no rename — the name is already generic.
Its vocabulary (IEC 62402 / EIA-724 wording: ``active``, ``not-recommended-for-new-design``,
``last-time-buy``, ``obsolete``, ``unknown``) lives in a deployment's own
``policy/registry/lifecycle_status.yaml``, never an enum here, same posture ``AssetContract``'s
``level``/``max_level`` take toward ``policy/classification/dimensions.yaml``.

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


class ImpactRow(BaseModel):
    """Generalizes ADR-0065 section D's ``ltb_decision {quantity, by, rationale, approved_by}``
    beyond last-time-buy alone — see the module docstring for why the type is renamed while its
    fields are not. The decided impact-mitigation for whichever disposition option a workflow's
    decide step actually resolved to."""

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
