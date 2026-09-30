"""THE PROVENANCE BLOCK — provenance is a field, never a join.

ADR-0035 §4. **No assertion enters a graph without its provenance riding in the same write.**

WHY THIS LIVES IN ``iagent_mesh`` AND NOT ONLY IN ``iagent``. The original shape is
``invincible-agent/src/iagent/provenance.py``, and it stays the reference copy — this module is
not a fork, it is the same shape made reachable from a package doc-tools actually depends on.
doc-tools depends on ``iagent_mesh``, never on ``iagent`` (7f measured: the stamp this module
provides was unreachable from doc-tools before this file existed, which is exactly what blocked
7f's ingress-user sensor from stamping what it ingests). Porting the shape here, rather than
adding a new dependency edge from doc-tools to ``iagent``, keeps the dependency graph the same
shape it already is — a domain-node scaffold importing ``iagent_mesh`` and nothing heavier.

WHY EMBEDDED AND NOT SIDECAR. A separate audit table you *could* join against always decays,
because the join is OPTIONAL and optional joins stop happening — the query that omits it is
shorter, works, and becomes the one everyone copies. Embedded provenance cannot be skipped:
reading the claim IS reading its origin.

This module is pure — no store, no transport — for the same reason the rest of this SDK's
interface surface is: the shape must be testable without a graph, and the graph must be
replaceable without touching the shape.

SOURCE AUTHORITY IS DISTANCE FROM TRUTH, NOT A RANKING OF PEERS (ADR-0035 §5). Where the
authoritative system is guarded, groups build convenient copies and those copies become
load-bearing while their export date recedes. So every assertion names the SAME
``authoritative_source`` and differs in ``obtained_via`` + ``as_of``. "Per the owning system, via
a manual export of unknown vintage" and "per the owning system, via last night's ETL" are
different facts, and a consumer must be able to see which one it has without asking anyone.

── `user-drop`, THE FIFTH RUNG, RULED BY ADR-0041 §2, 2026-08-17 ───────────────────────────────
A hand-carried document from an individual's inbox is a degradation path, and the farthest one
this vocabulary has. ``user-drop`` extends the existing ORDERED tuple at the far end —
``authoritative_source`` is unchanged by who carried the copy, only how far it travelled from the
system that owns the truth. ``as_of`` will very often be :data:`AS_OF_UNKNOWN` for a user drop,
which is exactly what that sentinel is for. ``standing`` for a user-dropped claim is
``"supervised"`` — born-supervised, ADR-0034's default, arrived at without an exception.

**A fifth ``obtained_via`` value is a change to a closed ordered tuple** — the order is meaningful
(nearest-to-truth first), not cosmetic, and ADR-0041's own Consequences section says so: every
consumer that reasons over :data:`OBTAINED_VIA` by position or exhaustiveness must be re-checked
when this tuple grows. It has now grown once, here.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "DIRECT",
    "ETL",
    "WAREHOUSE",
    "MANUAL_EXPORT",
    "USER_DROP",
    "OBTAINED_VIA",
    "ObtainedVia",
    "AS_OF_UNKNOWN",
    "PROV_DERIVED_FROM",
    "PROV_GENERATED_AT",
    "ProvenanceIncomplete",
    "ProvenanceBlock",
    "make_provenance",
    "validate_provenance",
    "require_provenance",
    "is_stale",
]

# HOW the claim was obtained — the degradation path, ordered nearest-to-truth. The ORDER is
# meaningful (it is distance from the authoritative system), not cosmetic. `user-drop` is the
# fifth rung, added at the far end per ADR-0041 §2 — see the module docstring.
DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP = (
    "direct", "etl", "warehouse", "manual-export", "user-drop")
OBTAINED_VIA = (DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP)

#: The same five values as a ``Literal`` for pydantic field typing — mirrors
#: ``SlotDecl.kind: Literal[SLOT_KINDS]`` in :mod:`iagent_mesh.graph_manifest`, the house pattern
#: for "one tuple is both the runtime membership check and the static type."
ObtainedVia = Literal[OBTAINED_VIA]  # type: ignore[valid-type]

# `as_of` when the truth-date is genuinely not knowable — e.g. an export with no recorded
# date, or a user drop with nothing attached. A SENTINEL, NEVER A BLANK: empty would collapse
# "we could not know" into "we forgot to record", and an analyst counting missing dates could
# not tell instrument failure from process fact.
AS_OF_UNKNOWN = "unknown"

# PROV terms, cherry-picked per the standards posture — a future auditor meets vocabulary they
# already know rather than a private dialect.
PROV_DERIVED_FROM = "http://www.w3.org/ns/prov#wasDerivedFrom"
PROV_GENERATED_AT = "http://www.w3.org/ns/prov#generatedAtTime"

_REQUIRED = ("authoritative_source", "obtained_via", "as_of", "ingested_at", "ingest_run",
             "standing")


class ProvenanceIncomplete(ValueError):
    """An assertion without complete provenance. Refused at WRITE, never at query.

    Raised directly by :func:`make_provenance`, :func:`validate_provenance` and
    :func:`require_provenance` — NOT surfaced as a pydantic field-validator on
    :class:`ProvenanceBlock`. A ``ValueError`` raised inside a pydantic validator is caught by
    pydantic-core and re-wrapped as a generic ``ValidationError``, which would make this
    exception's own name unreachable to a caller who catches it specifically — exactly the
    boundary-gate discipline :class:`iagent_mesh.interfaces.ServiceIdentityRefused` and
    :class:`iagent_mesh.write_results.WriteNotApplied` already follow: a caller that gates on
    "provenance was incomplete" must be able to catch that condition by name, not by string-
    matching a generic validation message.
    """


class ProvenanceBlock(BaseModel):
    """The stamp. Six required fields, one optional — the same six :func:`make_provenance` and
    :func:`validate_provenance` check, made a typed model so a caller who already has the fields
    in hand can construct one directly instead of going through the builder.

    ``standing`` IS FROZEN AT WRITE — the source's trust rung *at the moment this claim was made*.
    The record is immutable, and "what this source's standing is now" is a different fact from
    "what it was when this was written". Conflating them would let a later promotion retroactively
    upgrade evidence gathered under weaker standing, which is exactly the regime-mixing ADR-0034
    refuses.

    ``ingest_run`` chains this claim into PIPELINE provenance for free: claim → run → sensor →
    source object → ETag. Every link already exists; naming the run here is what assembles them
    into one lineage instead of four disconnected facts.

    **Prefer :func:`make_provenance` to constructing this directly.** The builder's per-field
    messages are the ones a doc-tools call site will actually see when it gets provenance wrong;
    this model's own field validators exist so a bypass of the builder (a future writer that
    populates the dict by hand, or round-trips one from storage) cannot land a value the builder
    would have refused — the same "re-check a block that did not come from the constructor"
    posture :func:`validate_provenance` states for the untyped-dict path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    authoritative_source: str
    """Names WHO OWNS THE TRUTH. The same value for every path to that truth — does not vary
    with ``obtained_via``."""
    obtained_via: ObtainedVia  # type: ignore[valid-type]
    as_of: str
    """The truth-date, or :data:`AS_OF_UNKNOWN` when it is genuinely not knowable. Never blank."""
    ingested_at: str
    ingest_run: str
    standing: str
    derived_from: Optional[str] = None
    """Maps to ``prov:wasDerivedFrom`` (:data:`PROV_DERIVED_FROM`) on serialization. Optional —
    not every claim derives from a named prior artifact."""

    @field_validator("authoritative_source", "as_of", "ingested_at", "ingest_run", "standing")
    @classmethod
    def _field_is_present(cls, v: str, info) -> str:
        if not v or not str(v).strip():
            raise ValueError(
                f"ProvenanceBlock.{info.field_name}='' — every field of provenance is required "
                f"at write; a claim that cannot say where it came from doesn't get written"
            )
        return v

    @model_validator(mode="after")
    def _obtained_via_is_a_known_rung(self) -> "ProvenanceBlock":
        if self.obtained_via not in OBTAINED_VIA:
            raise ValueError(
                f"ProvenanceBlock.obtained_via must be one of {OBTAINED_VIA}, got "
                f"{self.obtained_via!r} — the path IS the degradation, so an unknown path "
                f"cannot be scored"
            )
        return self

    def as_dict(self) -> dict:
        """The wire shape :func:`make_provenance` itself returns — a plain dict with
        ``derived_from`` present only when set, matching the original ``iagent.provenance``
        builder's output exactly so a consumer written against either shape reads the same keys.
        """
        block = {
            "authoritative_source": self.authoritative_source,
            "obtained_via": self.obtained_via,
            "as_of": self.as_of,
            "ingested_at": self.ingested_at,
            "ingest_run": self.ingest_run,
            "standing": self.standing,
        }
        if self.derived_from:
            block["derived_from"] = self.derived_from
        return block


def make_provenance(*, authoritative_source: str, obtained_via: str, as_of: Optional[str],
                     ingested_at: Any, ingest_run: str, standing: str,
                     derived_from: Optional[str] = None) -> dict:
    """Build the block. Every field is required; there are no convenient defaults.

    THE BUILDER DOC-TOOLS IMPORTS. Returns a plain ``dict`` — the wire shape every consumer
    (a graph write, a JSON serialization, a diff against a stored block) actually handles —
    rather than a :class:`ProvenanceBlock`, matching ``iagent.provenance.make_provenance``'s
    signature and return type exactly so a caller migrating from that module to this one changes
    only the import line.

    Raises :class:`ProvenanceIncomplete` by name — never a generic ``ValueError`` or a pydantic
    ``ValidationError`` — because this is the WRITE-SIDE gate ADR-0035 §4 names ("the claim that
    cannot say where it came from doesn't get written"), and a caller gating on that condition
    needs one exception type to catch.
    """
    if not authoritative_source:
        raise ProvenanceIncomplete(
            "authoritative_source is required — it names WHO OWNS THE TRUTH, and it is the "
            "same value for every path to that truth. A claim that cannot name its owning "
            "system is a claim whose distance from truth is unmeasurable")
    if obtained_via not in OBTAINED_VIA:
        raise ProvenanceIncomplete(
            f"obtained_via must be one of {OBTAINED_VIA}, got {obtained_via!r} — the path IS "
            f"the degradation, so an unknown path cannot be scored")
    if not as_of:
        raise ProvenanceIncomplete(
            f"as_of is required; use {AS_OF_UNKNOWN!r} when the truth-date is genuinely not "
            f"knowable. A BLANK collapses 'we could not know' into 'we forgot to record', and "
            f"those are different facts about the pipeline")
    if not ingest_run:
        raise ProvenanceIncomplete(
            "ingest_run is required — without it the claim cannot be chained back to the run, "
            "sensor and source object that produced it, and the lineage stops at this row")
    if not standing:
        raise ProvenanceIncomplete("standing is required (the source's rung AT WRITE TIME)")
    block = {
        "authoritative_source": authoritative_source,
        "obtained_via": obtained_via,
        "as_of": as_of,
        "ingested_at": ingested_at,
        "ingest_run": ingest_run,
        "standing": standing,
    }
    if derived_from:
        block["derived_from"] = derived_from      # -> prov:wasDerivedFrom on serialization
    return block


def validate_provenance(block: Any) -> None:
    """Re-check a block that did not come from :func:`make_provenance` — a future writer must
    not be able to bypass the constructor and land an unprovenanced claim."""
    if not isinstance(block, dict):
        raise ProvenanceIncomplete("provenance block must be a dict")
    missing = [f for f in _REQUIRED if not block.get(f)]
    if missing:
        raise ProvenanceIncomplete(
            f"provenance block is missing {missing} — an assertion without complete provenance "
            f"is refused at WRITE, because discovering it at query time means the corpus "
            f"already contains claims nobody can place")
    if block["obtained_via"] not in OBTAINED_VIA:
        raise ProvenanceIncomplete(f"bad obtained_via {block['obtained_via']!r}")


def require_provenance(assertion: dict, *, key: str = "provenance") -> dict:
    """WRITE-SIDE MANDATORY. Wrap any assertion-writer with this: it refuses the write rather
    than accepting a claim that cannot say where it came from.

    The doctrine line, so it is enforceable and not merely documented:
    **the claim that cannot say where it came from doesn't get written.**
    """
    validate_provenance((assertion or {}).get(key))
    return assertion


def is_stale(block: dict, *, now_date: str, max_age_days: int) -> Optional[bool]:
    """Is this claim older than the freshness contract? ``None`` means UNKNOWABLE.

    Returns ``None`` — never ``False`` — for ``as_of: unknown``. An unknown vintage is not
    "fresh"; it is a claim whose age cannot be established, and reporting that as "not stale"
    would be the optimistic default this codebase keeps refusing. A ``user-drop`` claim will
    very often carry :data:`AS_OF_UNKNOWN`, so this is the path that condition actually exercises
    most. Callers decide what unknowable is worth, which is the point of ADR-0035 §5: consumers
    judge distance, the model only records it.
    """
    if block.get("as_of") == AS_OF_UNKNOWN:
        return None
    from datetime import date

    def _d(s):
        y, m, d = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, d)

    try:
        return (_d(now_date) - _d(block["as_of"])).days > max_age_days
    except Exception:  # noqa: BLE001 — an unparseable date is unknowable, not fresh
        return None
