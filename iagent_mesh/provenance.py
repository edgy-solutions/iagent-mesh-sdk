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

── `steward-corrected`, THE SIXTH RUNG, RULED BY invincible-agent/lane/01's steward-correction
packet, 2026-10-10 ─────────────────────────────────────────────────────────────────────────────
A steward retyping a field that automated extraction got wrong is still not the authoritative
system — they are a human intermediary correcting a READING of it, the same kind of hop
``manual-export``/``user-drop`` already are, not a peer ranking by how trustworthy the correction
turns out to be (ADR-0035 §5's own warning: distance from truth, not a ranking of peers, applies
here too — an evidence-backed correction is not exempt from it). ``steward-corrected`` extends
the tuple at the same far end as ``user-drop``: the two rungs with no machine-direct path to the
authoritative system at all.

Two more optional fields ride on :class:`ProvenanceBlock` for this rung and no other:
``corrected_by`` (who) and ``extracted_value`` (what automated extraction produced before the
correction, kept for audit — the corrected value itself is just the field's own current content,
never a second copy here). They ride together, and only under this rung: a block whose
``obtained_via`` is ``steward-corrected`` must carry both; a block under any other rung must
carry neither. The pairing IS the "this row was corrected" fact — a stray ``corrected_by`` on a
``direct`` block would assert a correction that never happened.

A sixth value is, again, a change to the closed ordered tuple ADR-0041's Consequences section
already warned would need re-checking. This module's own
:func:`iagent_mesh.conformance.check_provenance_floor_contract` and
:func:`iagent_mesh.conformance.check_provenance_sources_contract` reason over :data:`OBTAINED_VIA`
by NAME (``DIRECT``, ``USER_DROP``), not by exhaustive position or count, so neither needed a
source change for this growth — but any fleet consumer that enumerates all rungs by position
still owes itself the same re-check this docstring keeps repeating.

:class:`ExtractionDefect`, below, is the companion record the same ruling names: filed once per
correction to the extraction pipeline's own admin queue, independent of what rides in the graph
row's ``ProvenanceBlock`` — the audit trail back to the pipeline, not a second copy of the stamp.

── `ingest_id`, ADDED 2026-09-30 ON THE v0.9.5 CUT ORDER ───────────────────────────────────────
The promotion store (ia-74/lane/74's `IngestGraph`/`IngestIndexes`) keys its cleanup on this one
field: a promotion or rejection deletes "everything whose block carries the id" by scoping
``MeshGraphWriter.delete_edges`` to an :class:`iagent_mesh.interfaces.EdgeIdentityFilter` bound on
``key=ingest_id`` alone. That only works if every fact-triple written for one ingest's provenance
shares the same ``key`` — this field is what a caller reads to supply that key, rather than
re-deriving or inventing a second identifier that could drift from the one actually stamped.
Optional, like ``derived_from``: not every provenance block names an ingest at all (a path-derived
or warehouse-sourced claim may have no single ingest act to point back to), so this is additive to
the six required fields, never a seventh required one.
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
    "STEWARD_CORRECTED",
    "OBTAINED_VIA",
    "ObtainedVia",
    "AS_OF_UNKNOWN",
    "PROV_DERIVED_FROM",
    "PROV_GENERATED_AT",
    "ProvenanceIncomplete",
    "ProvenanceBlock",
    "ExtractionDefect",
    "make_provenance",
    "validate_provenance",
    "require_provenance",
    "is_stale",
]

# HOW the claim was obtained — the degradation path, ordered nearest-to-truth. The ORDER is
# meaningful (it is distance from the authoritative system), not cosmetic. `user-drop` is the
# fifth rung, added at the far end per ADR-0041 §2; `steward-corrected` is the sixth, added at
# the same far end per the 2026-10-10 steward-correction ruling — see the module docstring.
DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP, STEWARD_CORRECTED = (
    "direct", "etl", "warehouse", "manual-export", "user-drop", "steward-corrected")
OBTAINED_VIA = (DIRECT, ETL, WAREHOUSE, MANUAL_EXPORT, USER_DROP, STEWARD_CORRECTED)

#: The same six values as a ``Literal`` for pydantic field typing — mirrors
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
    ingest_id: Optional[str] = None
    """Which ingest act produced this claim, when there is a single one to name. Optional, same
    discipline as ``derived_from`` — a path-derived or warehouse-sourced claim may have no one
    ingest to point back to. **This is the field a promotion/rejection cleanup scopes its graph
    delete by** (`EdgeIdentityFilter(key=ingest_id)` against `MeshGraphWriter.delete_edges`) — see
    the module docstring's "ingest_id, ADDED 2026-09-30" section."""
    corrected_by: Optional[str] = None
    """Who corrected this claim — set if and only if ``obtained_via`` is
    :data:`STEWARD_CORRECTED`. See the module docstring's "steward-corrected, THE SIXTH RUNG"
    section. Opaque, carried verbatim — this field does not parse it."""
    extracted_value: Optional[str] = None
    """What automated extraction produced for this claim BEFORE the correction, preserved for
    audit. Set if and only if ``obtained_via`` is :data:`STEWARD_CORRECTED`. May be blank — "the
    extraction produced nothing" is itself a legitimate defect to record, not an omission this
    field refuses. The corrected value is not duplicated here; it is whatever this claim's own
    field already holds."""

    @field_validator("authoritative_source", "as_of", "ingested_at", "ingest_run", "standing")
    @classmethod
    def _field_is_present(cls, v: str, info) -> str:
        if not v or not str(v).strip():
            raise ValueError(
                f"ProvenanceBlock.{info.field_name}='' — every field of provenance is required "
                f"at write; a claim that cannot say where it came from doesn't get written"
            )
        return v

    @field_validator("corrected_by")
    @classmethod
    def _corrected_by_is_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                "ProvenanceBlock.corrected_by='   ' — set it to who corrected the claim, or "
                "leave it unset; a blank value is neither"
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

    @model_validator(mode="after")
    def _corrected_fields_ride_only_with_steward_corrected(self) -> "ProvenanceBlock":
        if self.obtained_via == STEWARD_CORRECTED:
            if self.corrected_by is None or self.extracted_value is None:
                raise ValueError(
                    "ProvenanceBlock(obtained_via='steward-corrected') requires both "
                    "corrected_by and extracted_value — a correction with no corrector or no "
                    "record of what it replaced is not an auditable correction"
                )
        elif self.corrected_by is not None or self.extracted_value is not None:
            raise ValueError(
                f"ProvenanceBlock.obtained_via={self.obtained_via!r} but corrected_by/"
                f"extracted_value is set — those two fields assert 'this row was corrected', "
                f"which only obtained_via='steward-corrected' can be true of"
            )
        return self

    def as_dict(self) -> dict:
        """The wire shape :func:`make_provenance` itself returns — a plain dict with
        ``derived_from``/``ingest_id``/``corrected_by``/``extracted_value`` present only when
        set, matching the original ``iagent.provenance`` builder's output exactly so a consumer
        written against either shape reads the same keys.
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
        if self.ingest_id:
            block["ingest_id"] = self.ingest_id
        if self.corrected_by is not None:
            block["corrected_by"] = self.corrected_by
        if self.extracted_value is not None:
            block["extracted_value"] = self.extracted_value
        return block


class EvidenceRef(BaseModel):
    """ADDED 0.9.11. A structured, machine-locatable citation into the source document — which
    page, and a bounding box on that page — for a caller that can jump straight to the region
    (e.g. a PDF viewer rendering the citation inline) rather than parsing one of
    :attr:`ExtractionDefect.evidence`'s free-form strings. A sibling, not a replacement:
    ``evidence`` stays the required, always-present citation; ``evidence_ref`` is the optional,
    structured one for a source that actually has pages and coordinates to cite.

    **Coordinate convention, RULED 2026-10-21** (architect directive to doc-tools/7f,
    cortex-ui/master, this SDK): ``bbox`` is page-fraction, ``0..1``, origin TOP-LEFT — unit-free
    by construction, the same everywhere ``evidence_ref`` appears, so no sibling ``units`` key
    ever rides beside it. A producer that measures in layout pixels or word-layer points (e.g.
    ``gateway.py``'s own ``_evidence_ref`` dict today, which carries ``"units": "pt"|"px"``)
    converts to this page-fraction space BEFORE constructing one of these — this model refuses to
    carry the unconverted value or a unit tag for it.

    **``note``, RULED 2026-10-21** (architect, same dry-run decision, item 4): this SDK's shape
    won over the BFF's own free-string ``evidence_ref`` on row/header edits — the BFF's string
    becomes ``note`` on this model. The BFF (invincible-agent/lane/01-202) runs its own mirror of
    this shape until it imports this SDK at a version that carries this field.

    **``bbox`` is Optional, RULED 2026-10-21 (second ruling, same day)**: ``page`` may not be
    null — ``bbox`` may. A null ``bbox`` means "stated on this page, no box we can draw": a
    citation the source only places on a page, not at a drawable region of it. A card rendering
    this jumps to the page with no outline and labels it "on page N, no box", rather than
    fabricating a box or refusing the citation outright. A derived field carries no
    ``evidence_ref`` at all (ruled separately) — a null ``bbox`` is for a citation that IS
    page-located but has no finer locus, not for the absence of a citation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int
    """1-indexed page number, matching how a PDF viewer or a human reader names a page — not
    0-indexed, which would require every consumer to add 1 before rendering a citation."""
    bbox: Optional[tuple[float, float, float, float]] = None
    """``(x0, y0, x1, y1)``, each a fraction of the page in ``0..1``, origin TOP-LEFT: ``(x0, y0)``
    is the box's upper-left corner, ``(x1, y1)`` its lower-right corner — ``y`` increases
    DOWNWARD the page, not the bottom-left/upward convention a PDF's own content stream uses.
    Unit-free: a fraction of the page means the same thing regardless of the source's native DPI,
    point size, or pixel grid, which is why no ``units`` field exists on this model at all.
    ``None`` means the citation is page-located but has no drawable region — not "no citation"."""
    note: Optional[str] = None
    """ADDED 2026-10-21. Free-form text alongside the structured ``page``/``bbox`` citation — the
    BFF's own free-string ``evidence_ref`` (e.g. ``"page 1 column header 'Customer Part
    Number'"``) lands here, not as a second, looser shape for this model. ``None`` by default;
    when given, must be non-blank — a blank ``note`` is indistinguishable from omitting it, so
    this model refuses the ambiguity rather than silently accepting it."""

    @field_validator("page")
    @classmethod
    def _page_is_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError(
                f"EvidenceRef.page={v} — pages are 1-indexed; a page before the first page is "
                f"not a citation, it is a mistake"
            )
        return v

    @field_validator("note")
    @classmethod
    def _note_is_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                "EvidenceRef.note='   ' — set it to the cited text, or leave it unset; a blank "
                "value is neither"
            )
        return v

    @field_validator("bbox")
    @classmethod
    def _bbox_is_well_formed(cls, v: Optional[tuple[float, float, float, float]]
                              ) -> Optional[tuple[float, float, float, float]]:
        if v is None:
            return v
        x0, y0, x1, y1 = v
        if not all(0.0 <= c <= 1.0 for c in v):
            raise ValueError(
                f"EvidenceRef.bbox={v!r} — every coordinate is a page fraction in 0..1 (the "
                f"2026-10-21 ruling); a value outside that range is unconverted pixel/point "
                f"geometry, not a citation this model accepts"
            )
        if not (x1 > x0 and y1 > y0):
            raise ValueError(
                f"EvidenceRef.bbox={v!r} — (x1, y1) must be strictly greater than (x0, y0), or "
                f"the box has zero or negative area and cites nothing"
            )
        return v


class ExtractionDefect(BaseModel):
    """The admin-queue record invincible-agent/lane/01's steward-correction ruling (2026-10-10)
    names beside ``obtained_via='steward-corrected'``: filed once per correction, independent of
    what rides in the graph row's own :class:`ProvenanceBlock` — the audit trail back to the
    extraction pipeline, not a second copy of the stamp. The ruling names doc-tools' admin/7f
    queue as where this lands; this model only validates the shape, same as every other
    record family here.

    GENERIC TO ANY ARTIFACT A STEWARD CORRECTS — never to a notice, a PCN, or any other domain
    name, the same discipline :mod:`iagent_mesh.conformance`'s provenance-floor arms already
    state for a verb shape. The ruling's own field names (``notice``, ``extracted``, ``corrected``)
    are invincible-agent's domain vocabulary; this model generalizes them to ``artifact_id``,
    ``extracted_value`` and ``corrected_value`` so a deployment maps its own domain field onto
    this shape rather than this SDK learning a domain term.

    No ``corrected_by`` here, unlike :class:`ProvenanceBlock`'s field of the same name: the
    review-resolve task that produces one of these already carries its actor (an
    ``Initiator``/``on_behalf_of`` on the task act) — duplicating identity onto this record too
    would be a second place for it to drift from the task's own.

    THIS SDK DOES NOT FILE OR QUEUE ANYTHING. A deployment's own review-resolve path mints one of
    these per correction and routes it to its own admin queue.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    """The ingested item the correction applies to — opaque to this model, the same discipline
    :class:`iagent_mesh.interfaces.MeshArtifacts`'s own ``id`` already states."""
    pin_digest: str
    """Identifies the extractor pin active when the defective extraction ran — the ruling's own
    reason a new pin is a RE-extraction trigger: the ETag does not move, so the pin is the only
    thing that distinguishes a re-extraction from a no-op."""
    extracted_value: str
    """What automated extraction produced, before correction. Blank is a legitimate value here —
    "extraction produced nothing" is itself the defect being filed, not an omission this field
    refuses."""
    corrected_value: str
    """What the steward corrected it to."""
    evidence: tuple[str, ...] = ()
    """Cites what backs the correction — a page/section of the source document, a pin digest,
    anything machine-checkable. Same grammar, and the same non-empty requirement, as
    :attr:`iagent_mesh.systems_of_record.Origin.evidence` states for ``resolved_by='record'``: a
    correction with nothing cited is indistinguishable from a guess wearing a corrected label."""
    evidence_ref: Optional[EvidenceRef] = None
    """ADDED 0.9.11. The structured sibling to ``evidence`` above — a page/bbox citation, for a
    source that has pages and coordinates to cite. ``None`` (the default) means this correction
    cites nothing more locatable than ``evidence``'s own strings, true of every defect before
    this field existed and of any source (a spreadsheet cell, a database row) with no page or
    bounding box to name. This field does not relax ``evidence``'s own non-empty requirement —
    the two are independent; a correction can carry a structured ref with or without one."""

    @field_validator("artifact_id", "pin_digest", "corrected_value")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"ExtractionDefect.{info.field_name}='' — required; a defect record that cannot "
                f"say which artifact, which pin, or what it was corrected TO is not a record "
                f"anyone downstream can act on"
            )
        return v

    @field_validator("evidence")
    @classmethod
    def _evidence_is_nonempty(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError(
                "ExtractionDefect.evidence=() — a correction with nothing cited is "
                "indistinguishable from a guess wearing a corrected label"
            )
        return v


def make_provenance(*, authoritative_source: str, obtained_via: str, as_of: Optional[str],
                     ingested_at: Any, ingest_run: str, standing: str,
                     derived_from: Optional[str] = None,
                     ingest_id: Optional[str] = None,
                     corrected_by: Optional[str] = None,
                     extracted_value: Optional[str] = None) -> dict:
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
    if obtained_via == STEWARD_CORRECTED:
        if not corrected_by or extracted_value is None:
            raise ProvenanceIncomplete(
                "obtained_via='steward-corrected' requires both corrected_by and "
                "extracted_value — a correction with no corrector or no record of what it "
                "replaced is not an auditable correction")
    elif corrected_by is not None or extracted_value is not None:
        raise ProvenanceIncomplete(
            f"obtained_via={obtained_via!r} but corrected_by/extracted_value was supplied — "
            f"those two fields assert 'this row was corrected', which only "
            f"obtained_via='steward-corrected' can be true of")
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
    if ingest_id:
        block["ingest_id"] = ingest_id            # scopes a promotion/rejection cleanup delete
    if corrected_by:
        block["corrected_by"] = corrected_by
    if extracted_value is not None:
        block["extracted_value"] = extracted_value
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
    corrected_by = block.get("corrected_by")
    extracted_value = block.get("extracted_value")
    if block["obtained_via"] == STEWARD_CORRECTED:
        if not corrected_by or extracted_value is None:
            raise ProvenanceIncomplete(
                "obtained_via='steward-corrected' requires both corrected_by and "
                "extracted_value — a correction with no corrector or no record of what it "
                "replaced is not an auditable correction")
    elif corrected_by is not None or extracted_value is not None:
        raise ProvenanceIncomplete(
            f"obtained_via={block['obtained_via']!r} but corrected_by/extracted_value is "
            f"present — those two fields assert 'this row was corrected', which only "
            f"obtained_via='steward-corrected' can be true of")


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
