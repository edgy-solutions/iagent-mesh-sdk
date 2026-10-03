"""THE INGEST WIRE SHAPES — ADR-0021 (deterministic content-kind selection) and ADR-0041
(user-contributed documents, provenance-gated truth), made reachable from ``iagent_mesh`` so a
kind-source repo (doc-tools) and a routing repo can agree on one request shape, one stage
vocabulary, and one registry mechanism without either inventing its own.

── FOUR THINGS, AND WHY THEY ARE ONE MODULE ─────────────────────────────────────────────────
``IngestRequest`` — what starts an ingest. ``IngestStatus`` — where it is, as a closed stage
vocabulary. ``ContentKindRegistration`` — one row of the ADR-0021 mapping table (kind, passes,
outputs — or, for an Event kind, ``seeds_workflow``/``identity_field`` instead; see
:data:`CONTENT_KIND_BRANCHES`, 0.9.7). ``resolve_content_kind``/``registered_kinds`` — how a kind
is validated against that table, i.e. how ``content_kind`` is DERIVED FROM REGISTRATIONS rather
than living as a free-standing enum a registry could drift from. They are one module because
``IngestRequest``'s ``content_kind`` field is only meaningful in the presence of the registry
that validates it — the request shape and the vocabulary that governs it cannot be designed
apart from each other.

── NOT EVERY ARRIVAL IS A DOCUMENT, 0.9.7 ──────────────────────────────────────────────────
An Event kind (``branch="event"``) declares no extraction at all — it names a workflow to start
(``seeds_workflow``) and a field to dedupe arrivals on (``identity_field``). This answers
ia-01/lane/01's 2026-10-02 packet: a per-domain route (``POST /maintenance/events``) is withdrawn
in favour of the seam reading these two fields off the matched registration. The two branches
share one ``kind`` namespace and one resolver (:func:`resolve_content_kind` does not care which
branch it returns) because a caller asking "what do I do with this kind" always starts from the
same lookup — what differs is which fields the answer carries.

── THE KIND IS NEVER GUESSED, AND THIS MODULE DOES NOT GUESS EITHER ────────────────────────
ADR-0021's precedence rule is: (1) an explicit ``content_kind`` declaration wins, (2) a
path-derived fallback if absent, (3) **HALT** if neither yields a registered kind — never a
silent default, never an LLM. This module owns only the THIRD step's refusal
(:func:`resolve_content_kind` raises :class:`ContentKindUnregistered` by name on an unregistered
kind) and the registry shape the first two steps are checked against. Steps (1) and (2) —
reading ``manifest.metadata.content_kind`` and parsing an S3 prefix — are a driver concern this
SDK does not own, the same reason nothing here imports ``neo4j`` or ``weaviate-client``: those
belong to the repo that holds the object store, not to the interface.

**This deliberately does NOT follow :mod:`iagent_mesh.task_kinds`'s ``UNDECLARED`` pattern.**
``task_kinds.resolve`` is TOTAL by design — an unknown task kind renders read-only rather than
failing, because a UI card must draw something. An unregistered content kind is the opposite
case: ADR-0021 rules it a HALT, because silently routing unclassified content through a default
extractor is how the single flat ``mfg:ManufacturingStep`` kind this ADR replaces happened in the
first place. Same shared composer (:mod:`iagent_mesh.declarations`), same row-per-file
discipline, deliberately DIFFERENT resolution shape — TOTAL is the wrong answer here, so this
module does not import it from the sibling that got it right for a different reason.

── PROVENANCE RIDES IN THE SAME WRITE, FROM THE FIRST REQUEST ──────────────────────────────
``IngestRequest.provenance`` is required, not optional. ADR-0035 §4's rule — "no assertion enters
a graph without its provenance riding in the same write" — starts at the door, not at the first
extracted triple: the door is where ``obtained_via`` is actually known (ADR-0041 §2, "different
watch path → different provenance, mechanically"), and an ``IngestRequest`` that let provenance be
filled in later would be the optional join ADR-0035 refuses, one layer earlier.
"""
from __future__ import annotations

from typing import Iterable, Literal, Optional
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .declarations import DeclarationError, compose_rows, load_rows
from .interfaces import Initiator
from .provenance import ProvenanceBlock

__all__ = [
    "INGEST_STAGES",
    "IngestStage",
    "CONTENT_KIND_BRANCHES",
    "ContentKindBranch",
    "IngestRequest",
    "IngestStatus",
    "ContentKindRegistration",
    "ContentKindUnregistered",
    "resolve_content_kind",
    "registered_kinds",
    "load_content_kind_registrations",
    "compose",
    "validate_dir",
]

# ── THE STAGE VOCABULARY, CLOSED, ORDERED NEAREST-TO-ARRIVAL FIRST ──────────────────────────
#: `received`    the door accepted the object; provenance stamped; not yet extracted
#: `extracting`  the registered kind's passes are running (ContentKindRegistration.passes)
#: `review`       extraction complete; sitting at the grouped review surface (ADR-0041 §1/§5),
#:                where the architect's `document_promotion` task is created
#: `promoted`    a decision record + promotion fact landed (ADR-0041 §5); authority written
#: `rejected`    a HUMAN decision swept the claim (ADR-0041 §6, property-keyed sweep)
#: `failed`      a MECHANICAL halt — unclassifiable kind (ADR-0021 rule 3) or an
#:               extraction error. Kept separate from `rejected` for the same reason
#:               `refused`/`failed` stay separate on the write-result vocabulary: a
#:               human declined (`rejected`) and a pipeline could not proceed (`failed`)
#:               have different remedies — a disposition decision, or a kind/registry fix.
#:
#: RENAMED 0.9.7, same state, not a seventh value beside it: this was `awaiting_disposition`
#: through 0.9.6. ia-01/lane/01 flagged that the architect's own `document_promotion` ruling
#: names the stage `review` while this module's docstring already described the identical state
#: ("extraction complete; sitting at the grouped review surface") under the older name — a
#: second name for one state, not two states. Ruled a rename, not an addition: the fleet's
#: `ingest_status.py` (which mirrors this tuple) moves with it, per ia-01's own packet.
INGEST_STAGES = ("received", "extracting", "review", "promoted", "rejected", "failed")

#: The vocabulary as a type for field annotations — same "tuple is both the membership check and
#: the static type" pattern as :data:`iagent_mesh.provenance.ObtainedVia`.
IngestStage = Literal[INGEST_STAGES]  # type: ignore[valid-type]

#: Stages that are TERMINAL — an ingest in one of these does not move again. Named because
#: `rejected` and `failed` both need a `detail`, for different reasons, and a caller checking
#: "is this one still live" should not have to enumerate the other four by hand.
_TERMINAL_STAGES = ("promoted", "rejected", "failed")

#: Stages whose `detail` is REQUIRED — the two that end an ingest without landing it, so a
#: consumer reading the status is told WHY rather than only THAT. `promoted` is also terminal but
#: needs no `detail`: its own `promotion_ref` (ADR-0041 §5) is the reason, living on the
#: promotion fact this module does not model — the SDK does not re-carry a field another
#: document already owns.
_DETAIL_REQUIRED_STAGES = ("rejected", "failed")


class ContentKindUnregistered(LookupError):
    """A ``content_kind`` reached :func:`resolve_content_kind` with no matching row.

    ADR-0021's precedence rule 3: **HALT if unclassifiable, never fall through to a default
    kind, never an LLM.** Raised by name — not returned as a sentinel row the way
    :data:`iagent_mesh.task_kinds.UNDECLARED` is — so a caller's halt path can catch exactly this
    condition rather than string-matching a generic lookup failure.
    """


#: Two shapes an arriving artifact's registration can declare, ADDED 0.9.7 answering ia-01's
#: first open question: `document` is the original shape — the kind runs extraction `passes`
#: and stamps `outputs`. `event` is new — the kind names a workflow to start (`seeds_workflow`)
#: and a field to dedupe arrivals on (`identity_field`); it runs no extraction pass, because
#: what arrived is not something to extract FROM, it is the input TO something already running.
#: Closed, ordered, same "tuple is both the membership check and the static type" pattern as
#: :data:`INGEST_STAGES`.
CONTENT_KIND_BRANCHES = ("document", "event")

#: The vocabulary as a type for field annotations.
ContentKindBranch = Literal[CONTENT_KIND_BRANCHES]  # type: ignore[valid-type]


class ContentKindRegistration(BaseModel):
    """One row of ADR-0021's mapping table: ``(kind-source value → kind → extractor-config →
    BAML-set → target OntologyClass)``, collapsed to the fields a kind-source repo needs to
    answer "what do I run, what does it produce, and who can promote it" — ``passes`` folds
    extractor-config and BAML-set into one ordered sequence of named extraction passes,
    ``outputs`` is the target ``OntologyClass`` kind(s) the ``INSTANCE_OF`` edge is stamped
    against, and ``domain`` (0.9.7) is the kind's HOME audience for the promotion task ADR-0041
    §5 opens on it, where one exists.

    **BRANCHES, ADDED 0.9.7** — answering ia-01/lane/01's 2026-10-02 packet. Not every arriving
    artifact is a document to extract: an ``Event`` kind (``branch="event"``) names a workflow to
    start on arrival (``seeds_workflow``) and a field to dedupe on (``identity_field``) instead of
    running passes. See :data:`CONTENT_KIND_BRANCHES`. ``branch="document"`` is the default and
    the original shape — ``passes``/``outputs`` required, ``seeds_workflow``/``identity_field``
    absent.

    **THIS SDK DOES NOT SHIP ANY ROWS.** The mapping table is "chartable, version-able,
    code-owned" per ADR-0021, colocated with the plugin registry — which lives in doc-tools, not
    here, the same reason :mod:`iagent_mesh.task_kinds` ships no domain species of its own.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    """The registered kind name, e.g. ``"work-instruction"``. Opaque to this module — never
    parsed, only compared for equality against an ``IngestRequest.content_kind``."""

    branch: ContentKindBranch = "document"  # type: ignore[valid-type]
    """ADDED 0.9.7. Which of :data:`CONTENT_KIND_BRANCHES` this row is. Governs which other
    fields on this row are required versus forbidden — see ``_branch_shape_is_consistent``
    below."""

    passes: tuple[str, ...] = ()
    """The extraction passes this kind runs, IN THE ORDER THEY RUN — e.g.
    ``("manufacturing.baml::ExtractWorkInstructions",)``. Required, non-empty, for
    ``branch="document"`` only: a document kind with no pass is not a kind, it is a row someone
    forgot to finish; an event kind runs no pass at all (see ``branch``). Ordered for the same
    reason :attr:`iagent_mesh.task_kinds.TaskKind.accepts` is ordered rather than a set — a
    pipeline that runs passes in sequence has a sequence to declare, and a set would let
    composition silently reorder it."""

    outputs: tuple[str, ...] = ()
    """The target ``OntologyClass`` kind(s) this registration's passes stamp via ``INSTANCE_OF``
    — e.g. ``("mfg:WorkInstruction",)``. Required, non-empty, for ``branch="document"`` only —
    ADR-0021's whole point is that an extracted instance is reachable through its class chain,
    and a document registration with no declared output is a kind whose instances the routing
    graph still cannot reach. An event kind stamps nothing; it starts a workflow instead."""

    seeds_workflow: Optional[str] = None
    """ADDED 0.9.7, ia-01's second question. Required for ``branch="event"``, forbidden for
    ``branch="document"``. The workflow this Event kind starts on arrival, with the artifact as
    its input — e.g. the maintenance bridge's seam starting a Restate workflow for an arriving
    ``maintenance-fault-event``. Replaces a per-domain route (``POST /maintenance/events`` is
    withdrawn in favour of this): the seam reads ``seeds_workflow`` off the matched registration
    rather than branching on the caller's URL."""

    identity_field: Optional[str] = None
    """ADDED 0.9.7, ia-01's third question. Required for ``branch="event"``, forbidden for
    ``branch="document"``. Names which field of the arriving artifact is this Event kind's
    identity — e.g. ``"event_id"`` for ``maintenance-fault-event``. The seam dedupes arrivals on
    it; this module does not perform the dedupe (that is Lane 1's seam, keyed via Restate's
    ``run``/``send``), it only declares which field is the key."""

    domain: Optional[str] = None
    """ADDED 0.9.7, ADDENDUM CORRECTED BY THE ARCHITECT. The promotion task the grouped-review
    surface opens on this kind (ADR-0041 §5) is granted to an audience keyed
    ``document_promotion:<domain>`` where a domain exists — but not every kind has one.
    ``None`` means this kind declares no HOME domain; a generic kind (``pdf``,
    ``engineering-document``, ``doors-export``) is read by many domains, and ITS artifacts'
    origin resolves per-artifact from evidence (:class:`iagent_mesh.systems_of_record.Origin`,
    ``resolved_by="record"``/``"steward"``), not from a fixed field on the kind. Ruled optional,
    not required: an earlier draft of this field required it on every kind, which is exactly the
    hazard the drop-domains prompt identified — forcing a generic kind to declare a domain it
    does not have. Set it only for a kind whose outputs always belong to one domain."""

    @field_validator("kind")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(
                f"ContentKindRegistration.{info.field_name}='' — a blank {info.field_name} "
                f"cannot be matched or granted against, which makes the row unreachable rather "
                f"than general"
            )
        return v

    @field_validator("seeds_workflow", "identity_field", "domain")
    @classmethod
    def _optional_field_is_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                f"ContentKindRegistration.{info.field_name}='' — omit the field (None) rather "
                f"than binding it to nothing"
            )
        return v

    @field_validator("passes", "outputs")
    @classmethod
    def _sequence_is_unique(cls, v: tuple[str, ...], info) -> tuple[str, ...]:
        seen = [x for i, x in enumerate(v) if x in v[:i]]
        if seen:
            raise ValueError(
                f"ContentKindRegistration.{info.field_name} repeats {sorted(set(seen))}"
            )
        return v

    @model_validator(mode="after")
    def _branch_shape_is_consistent(self) -> "ContentKindRegistration":
        if self.branch == "event":
            if self.passes or self.outputs:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='event') declares "
                    f"passes/outputs — an event kind is not extracted, it seeds a workflow; "
                    f"passes/outputs belong to branch='document' rows only"
                )
            if self.seeds_workflow is None:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='event') requires "
                    f"seeds_workflow — an event kind with nothing to start is not a kind, it is "
                    f"a row someone forgot to finish"
                )
            if self.identity_field is None:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='event') requires "
                    f"identity_field — the seam dedupes arrivals on it; with none declared, "
                    f"every arrival is a new one"
                )
        else:  # branch == "document"
            if not self.passes:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='document') requires "
                    f"non-empty passes — empty means this kind runs nothing, which is not a "
                    f"registration, it is a placeholder"
                )
            if not self.outputs:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='document') requires "
                    f"non-empty outputs — empty means this kind produces nothing the routing "
                    f"graph can reach"
                )
            if self.seeds_workflow is not None:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='document') declares "
                    f"seeds_workflow — that field belongs to branch='event' rows only"
                )
            if self.identity_field is not None:
                raise ValueError(
                    f"ContentKindRegistration(kind={self.kind!r}, branch='document') declares "
                    f"identity_field — that field belongs to branch='event' rows only"
                )
        return self


def resolve_content_kind(
    kind: str, registrations: Iterable[ContentKindRegistration]
) -> ContentKindRegistration:
    """The row for ``kind``, or a loud, named refusal.

    NOT total, unlike :func:`iagent_mesh.task_kinds.resolve` — see the module docstring for why
    an unregistered content kind is ADR-0021's HALT case rather than a degrade-visibly case.
    """
    for r in registrations:
        if r.kind == kind:
            return r
    raise ContentKindUnregistered(
        f"{kind!r} is not a registered content kind. ADR-0021 rule 3: this halts the ingest "
        f"rather than falling through to a default kind or asking an LLM to guess one. "
        f"Registered kinds: {sorted(r.kind for r in registrations)}"
    )


def registered_kinds(registrations: Iterable[ContentKindRegistration]) -> tuple[str, ...]:
    """The picker's options, sorted — ADR-0021 / ADR-0041 §4's select-from-authorized-set
    applied to content kind: **the legal set of kinds IS the registered rows**, not a
    free-standing ``ContentKind`` enum a registry could drift out of step with. A caller building
    a kind picker (human-facing, per ADR-0041 §4's "classifier suggests, human confirms into
    ``manifest.metadata.content_kind``") offers exactly this tuple and nothing an unregistered
    string could satisfy.
    """
    return tuple(sorted(r.kind for r in registrations))


def load_content_kind_registrations(directory: Path | str) -> list[ContentKindRegistration]:
    """Every declared row in one directory, validated, sorted by kind. Same composer, same
    tombstone rule, same duplicate-key refusal as :func:`iagent_mesh.task_kinds.load_task_kinds`
    — see :mod:`iagent_mesh.declarations` for the mechanism this delegates to."""
    return load_rows(directory, key_field="kind", builder=lambda raw: ContentKindRegistration(**raw),
                     label="content kind registration", error=DeclarationError)


def compose(seed_dir: Path | str, overlay_dirs: Iterable[Path | str] = ()
           ) -> list[ContentKindRegistration]:
    """ADR-0036 composition for content-kind registrations — a deployment's overlay adds or
    replaces rows the seed does not ship, same mechanism as every other declaration family in
    this SDK."""
    return compose_rows(seed_dir, overlay_dirs, key_field="kind",
                        builder=lambda raw: ContentKindRegistration(**raw),
                        label="content kind registration", error=DeclarationError)


def validate_dir(directory: Path | str) -> list[ContentKindRegistration]:
    """The callable a mapping-table PR gate and a seed job both import — same split rationale as
    :func:`iagent_mesh.task_kinds.validate_dir`: one function, so a row that passes one gate and
    fails the other cannot happen."""
    return load_content_kind_registrations(directory)


class IngestRequest(BaseModel):
    """What starts an ingest. One request, one object, one declared (or undeclared) kind, one
    provenance block — the wire shape a kind-source repo and a routing repo agree on instead of
    each inventing its own.

    ``content_kind`` IS OPTIONAL HERE AND THAT IS ADR-0021's PRECEDENCE RULE, NOT A GAP. A set
    value is the explicit declaration channel (rule 1, wins over everything). ``None`` means
    "derive it from the path" (rule 2), which is a driver-side concern this SDK does not perform
    — the field being optional is what LEAVES ROOM for that fallback rather than forcing a caller
    who has no declared kind yet to invent one. Whatever kind a caller eventually settles on,
    set or derived, is checked against the registry with :func:`resolve_content_kind` — this
    model does not check it inline, because checking it here would require the registry at
    construction time, and a request may exist before the registry resolution runs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_ref: str
    """The source object's identifier — an S3 key, a URI, whatever the door that accepted it
    uses to name it. OPAQUE TO THIS MODULE, never parsed here, same discipline as
    :attr:`iagent_mesh.interfaces.EdgeIdentity.key`: path-derived kind fallback (ADR-0021 rule 2)
    is a driver concern, not this SDK's."""

    content_kind: Optional[str] = None
    """The explicit declaration, if the door has one (ADR-0021 rule 1). ``None`` defers to
    path-derived fallback or HALT — see the class docstring."""

    domain_type: Optional[str] = None
    """The coarser, already-wired kind-source (ADR-0021 §"what kind-sources actually exist
    today") — plugin selection, one level up from ``content_kind``. Carried through rather than
    re-derived, since the door that builds this request already has it."""

    provenance: ProvenanceBlock
    """Required from the first request, not attached later — see the module docstring's
    "PROVENANCE RIDES IN THE SAME WRITE" section."""

    initiator: Initiator
    """Who, or what, is dropping this object — a person for a user-drop (ADR-0041), a service or
    delegate identity for a sensor-driven ingest."""

    @field_validator("object_ref")
    @classmethod
    def _object_ref_is_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "IngestRequest.object_ref='' — every ingest names the object it ingests; a "
                "blank ref cannot be chained to the run, sensor and source object that produced it"
            )
        return v

    @field_validator("content_kind", "domain_type")
    @classmethod
    def _optional_field_is_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                f"IngestRequest.{info.field_name}='' — omit the field (None) to mean 'not "
                f"declared', rather than binding it to nothing"
            )
        return v


class IngestStatus(BaseModel):
    """Where one ingest is, right now. The write-side sibling of
    :class:`iagent_mesh.write_results.MeshWriteResult`: one type, a closed stage vocabulary, and
    a ``detail`` that is required wherever silence would hide the reason — same discipline,
    different vocabulary, because an ingest's lifecycle is longer than one write's outcome.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: IngestStage  # type: ignore[valid-type]
    detail: Optional[str] = None
    """Why, for ``rejected`` or ``failed`` — required on those two (see
    :data:`_DETAIL_REQUIRED_STAGES`) for the same reason ``MeshWriteResult.detail`` is required
    on everything but a clean ``written``: a terminal state with no reason reaches an operator as
    "something happened" and is unactionable."""

    @model_validator(mode="after")
    def _detail_present_where_required(self) -> "IngestStatus":
        if self.stage in _DETAIL_REQUIRED_STAGES and not (self.detail and self.detail.strip()):
            raise ValueError(
                f"IngestStatus(stage={self.stage!r}) requires detail — a {self.stage!r} with no "
                f"reason is unactionable, the same rule MeshWriteResult applies to its own "
                f"non-clean outcomes"
            )
        return self

    def is_terminal(self) -> bool:
        """``True`` once this ingest will not move again. See :data:`_TERMINAL_STAGES`."""
        return self.stage in _TERMINAL_STAGES
