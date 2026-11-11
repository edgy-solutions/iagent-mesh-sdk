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

``ImpactRow`` is "the where-used impact-table row" — the architect's 2026-11-06 correction named
it section E with no field-level text findable anywhere at the time, so v0.9.16 shipped a
three-field ``{part_ref, used_by, quantity}`` judgment call, explicitly flagged as not a
recovered spec. **That shape was wrong, and shipped anyway** — ADR-0065 was drafted the same day
as invincible-agent#299, its real section is **section 4** (not E), and lane 01's two 2026-11-07
packets (16:41, then a superseding 17:09 ruling) were sitting unread in ``sessions/`` when ca
tagged and published v0.9.16 to PyPI. The architect ruled on #299's four questions 2026-11-07, via
Chris — ruling 4 replaces the three-field shape with the nine fields below. PyPI does not allow
re-uploading a version, so the fix is forward: this module now ships the ruled shape as of
v0.9.17, and v0.9.16 stays published with the superseded one (see ``CHANGELOG.md``). Lesson: a
tag is a live-state claim too — check for unread packets before cutting one, not just before
writing a handoff.

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

This module ships the row shapes and the emitter does not — but unlike
:func:`iagent_mesh.systems_of_record.validate_connectors_known` (which takes an
ALREADY-LOADED ``known_connectors`` iterable because that registry is arbitrary per deployment),
``status``'s vocabulary lives at a FIXED, served path — ``policy/registry/lifecycle_status.yaml``
— so this module reads that file itself (v0.9.16, per the architect's correction: "reads the
served registry file; it does not define the vocabulary"). "Reads" and "defines" are different
things: :func:`load_lifecycle_status_vocabulary` performs the file I/O; the FILE'S CONTENTS are
still the deployment's own (IEC 62402 / EIA-724 wording — ``active``,
``not-recommended-for-new-design``, ``last-time-buy``, ``obsolete``, ``unknown`` — is a
documentation example, not a shipped default; this module ships zero rows). Checking a
``LifecycleStatus.status`` against the loaded vocabulary is :func:`validate_status_known`, a free
function rather than a field validator, for the same reason :func:`iagent_mesh.asset_contract.validate`
is free-standing: the frozen row does not have the file path at construction time, and a row may
exist before the vocabulary is loaded.

This module does not ship the emitter or the ``obsolescence_resolution`` workflow runner, the
same division every other row-shape module in this SDK draws
(:mod:`iagent_mesh.maintenance_bridge`, :mod:`iagent_mesh.asset_contract`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "LifecycleStatus",
    "LtbDecision",
    "ImpactRow",
    "DataProvenance",
    "LifecycleStatusError",
    "UnknownLifecycleStatus",
    "load_lifecycle_status_vocabulary",
    "validate_status_known",
]


class LifecycleStatusError(ValueError):
    """``policy/registry/lifecycle_status.yaml`` is malformed. Always names the file, same
    reasoning as :class:`iagent_mesh.declarations.DeclarationError`: "a vocabulary file is
    invalid" is not actionable at load time."""


class LifecycleStatus(BaseModel):
    """``lifecycle_status {status, source, as_of, successor?}`` — ADR-0065 section D, unchanged.
    See the module docstring for the absent-vs-null distinction this field kind exists to carry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Optional[str] = None
    """An open string against a deployment's own ``policy/registry/lifecycle_status.yaml`` —
    never an enum here, per generic-at-birth. Check membership with :func:`validate_status_known`
    against a vocabulary loaded by :func:`load_lifecycle_status_vocabulary`; this field itself is
    never checked at construction time (the row does not have the registry path). ``None`` means
    assessed, none known (see module docstring); it is a positive fact, not an absence — the
    absence case is one level up, on whatever record carries this field at all, and is NEVER
    checked against the vocabulary (see :func:`validate_status_known`)."""
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


class DataProvenance(BaseModel):
    """Dataset URN, as-of, and ticket id — the triple the architect's ruling says rides on
    :attr:`ImpactRow.data_provenance` "as on every served table." No existing shared shape for
    this triple was found anywhere in this SDK (checked :mod:`iagent_mesh.provenance`'s own,
    richer ``ProvenanceBlock``, :mod:`iagent_mesh.measure_series`, :mod:`mcp_server.bff_tools`);
    this is this module's own minimal typed mirror of the ruling's three nouns, flagged in case a
    shared one already exists elsewhere that this search missed.

    **`dataset_urn`/`ticket_id` can say ABSENT, ADDED 0.9.19** — lane 74's `#337` packet named the
    real gap: a served row with no catalogue entry has no dataset URN, and a row with no broker
    read has no ticket; re-exporting that row forced inventing both as placeholder strings.
    ``None`` on either field means absent, never a placeholder. `as_of` stays required — this row
    is only ever answered from data that was current as of SOME moment, absent sourcing or not;
    only the two sourcing facts, not the timestamp, can be missing. **This ships absence-marking
    only.** Holding more than one provenance entry per row (lane 74's other `#337` ask, the
    fleet's own ``{inputs: [...], absent: {...}}`` shape) is a separate, still-unruled question —
    not part of this change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_urn: Optional[str] = None
    """``None`` means absent — no catalogue entry — never a placeholder string. ADDED 0.9.19."""
    as_of: str
    """ISO-8601, this SDK's house convention for a wire timestamp — never ``datetime``. Stays
    required: unlike :attr:`dataset_urn`/:attr:`ticket_id`, this is never the fact that's absent."""
    ticket_id: Optional[str] = None
    """``None`` means absent — no broker read — never a placeholder string. ADDED 0.9.19."""

    @field_validator("dataset_urn", "ticket_id")
    @classmethod
    def _optional_field_is_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                f"DataProvenance.{info.field_name}='' — use None for absent, not a blank string"
            )
        return v


class ImpactRow(BaseModel):
    """The where-used impact-table row, ADR-0065 **section 4** (invincible-agent#299), ruled by
    the architect 2026-11-07 via Chris — ruling 4 on #299's four questions. One row per
    (``end_item``, ``program``, ``component``) triple. Supersedes the three-field
    ``{part_ref, used_by, quantity}`` shape v0.9.16 shipped before this ruling reached ca; see the
    module docstring for how that happened."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    end_item: str
    """The end item's identity."""
    program: str
    """The program the end item is sustained under — joined from openddil ADR-0056 section 8's
    sustained-under relation, never from the BOM."""
    component: str
    """The part the where-used question was asked about, by identity."""
    qty_per: int
    """The part's rolled-up quantity per end item, through every level."""
    population: Optional[int] = None
    """The fielded count of that end item on that program. ``None`` means no source for this
    count exists today — NEVER reported as ``0``, which would claim a sourced, counted-zero
    population."""
    stock: Optional[int] = None
    """The part's stock on hand for that program. Same absent-is-not-zero rule as
    :attr:`population`."""
    configuration: str = "as_designed"
    """``as_designed``, ``as_built``, or ``as_maintained`` per the ruling — an open string, not a
    ``Literal``/``Enum``, per generic-at-birth, matching :attr:`LifecycleStatus.status`'s own
    reasoning. Also an argument of the where-used query this row answers; the ruling's default is
    ``as_designed``. A configuration with no data for the end item must be refused loudly by
    whatever resolver answers the query, never served as an empty table — this module ships the
    row only, not that refusal (see the module docstring's emitter/runner split)."""
    as_of: str
    """ISO-8601. When the data this row was answered from was current."""
    data_provenance: DataProvenance
    """Dataset URN, as-of, and ticket id — see :class:`DataProvenance`, including the 0.9.19
    absence-marking it gained and that change's explicit scope line."""


class UnknownLifecycleStatus(LookupError):
    """A ``status`` value is not in the loaded vocabulary. Raised by :func:`validate_status_known`
    — never silently: a typo'd or retired status must halt a reader, the same way
    :class:`iagent_mesh.ingest.ContentKindUnregistered` halts rather than resolving as if the
    kind simply never matches."""


def load_lifecycle_status_vocabulary(path: Path | str) -> tuple[str, ...]:
    """Read one deployment's ``policy/registry/lifecycle_status.yaml`` and return its vocabulary
    of legal :attr:`LifecycleStatus.status` values, in file order.

    This module READS the file; it does not DEFINE what is in it — the expected shape is a
    mapping with a ``statuses`` key naming a non-empty list of non-blank strings. The values
    themselves (``active``, ``obsolete``, whatever a deployment names) are the deployment's own;
    this function does not validate them against IEC 62402/EIA-724 or any other fixed list.
    """
    import yaml

    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if raw is None:
        raise LifecycleStatusError(
            f"{p.name} is empty — an empty vocabulary file is not a vocabulary"
        )
    statuses = raw.get("statuses") if isinstance(raw, dict) else None
    if not isinstance(statuses, list) or not statuses or not all(
        isinstance(s, str) and s.strip() for s in statuses
    ):
        raise LifecycleStatusError(
            f"{p.name}: expected a mapping with a non-empty `statuses` list of non-blank strings"
        )
    return tuple(statuses)


def validate_status_known(status: Optional[str], vocabulary: tuple[str, ...]) -> None:
    """Raise :class:`UnknownLifecycleStatus` if ``status`` is not ``None`` and not in
    ``vocabulary`` (as loaded by :func:`load_lifecycle_status_vocabulary`).

    ``status=None`` is NEVER checked — it means "assessed, none known" (see the module
    docstring's absent/null distinction), a positive fact independent of the vocabulary's
    contents, not a value the vocabulary could contain or omit.
    """
    if status is not None and status not in vocabulary:
        raise UnknownLifecycleStatus(
            f"status={status!r} is not in the deployment's lifecycle-status vocabulary "
            f"{list(vocabulary)} — a typo'd or retired status must halt, not resolve as if "
            f"unassessed"
        )
