"""A graph manifest: what a chain IS, and the one helper that makes it a mesh verb.

ADR-0046 §1 — one graph, one verb, full contract. ADR-0046 §2 refuses ``run_any_graph`` by
name, and the models below are what make that refusal STRUCTURAL rather than a rule people
follow: a host learns a graph exists only from a ratified row, so a graph module with no row is
invisible to the mesh.

── WHY THIS LIVES IN THE SDK AND NOT IN THE HOST ENGINE ────────────────────────────────────
Ruled 2026-09-08. The first draft of these models lived in ``agent_fleet/graph_host/``, and
that placement forks the schema the first time anyone runs their own host:

    policy/graphs/<id>.yaml   WHAT a chain is — its contract.        Reviewed like a grant.
    THIS MODULE               HOW a chain joins, and how it acts.    One implementation.
    engine-lg                 WHERE it runs by default.              Thin consumer.

**"Plug into our host" versus "run your own" becomes a deployment choice rather than a second
implementation.** A team that hosts their own graph (ADR-0046 §8.5's route C) imports the same
loader, validates against the same schema, and registers with the same helper; their manifest
never enters the platform repo or its overlay. If the loader lived in the host, route C would
be a rewrite and the schema would fork the day someone copied it.

**The same property is what lets the merge gate work.** Validation runs in the private policy
repo's PR gate AND fail-closed in the seed cronjob (ADR-0050 premise correction 2 — the
platform repo has no CI job validating ``policy/``). Two rails, one validator: whichever rail
runs, it imports :func:`validate_dir` from here. A validator copied into either rail is a copy
that drifts, and the drift is invisible until a row passes one gate and fails the other.

── COMPOSITION IS ADR-0036'S, UNCHANGED ────────────────────────────────────────────────────
The seed ships platform graphs; a work-side overlay adds, replaces or deletes; composition
happens at the repo and the composed set passes the SAME validation. :func:`compose` implements
ADR-0036's stated merge algebra verbatim — *"overlay entries replace or delete by key, seed
applies where the overlay is silent"* — at the granularity that ADR names as the lean,
per-entry, because that is what makes deletion natural. **Deletion must be expressible** (§3c):
without it, the first customer who does not want a seeded graph registered in their mesh has to
fork the seed.

:func:`load_manifests` and :func:`compose` both take PATHS. Neither knows which repo a row came
from, and that is the point — only that it validated.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "SLOT_KINDS",
    "REF_COSMETIC",
    "RefusalViolation",
    "enforce_refusal",
    "ref_basis",
    "REFUSAL_DISPOSITIONS",
    "SlotDecl",
    "GraphManifest",
    "ManifestError",
    "manifest_ref",
    "load_manifests",
    "compose",
    "validate_dir",
    "json_schema",
    "registration_payload",
    "register_graph",
]

#: The four-kind slot vocabulary, reproduced verbatim and in order from the engines that
#: established it, so a consumer reading declarations from a hosted graph sees ONE vocabulary
#: rather than a fourth that agrees.
SLOT_KINDS = ("spoken-mandatory", "spoken-optional", "handle", "ceremony")

#: What a graph does when an inner verb refuses for the initiator. DECLARED PER ROW, never
#: decided at runtime — ADR-0049 Ruling 2's named hole is a choice about what an answer MEANS,
#: and a graph choosing per-invocation would give two callers different contracts for one verb.
REFUSAL_DISPOSITIONS = ("fail", "named-hole")


class ManifestError(ValueError):
    """A ratified row is invalid. Always names the file, because 'a manifest is invalid' is
    not actionable at merge time and naming the file is what makes it fixable without a bisect.
    """


class SlotDecl(BaseModel):
    """One declared slot — the same record shape the fleet's ``slots_for()`` emits."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal[SLOT_KINDS]  # type: ignore[valid-type]
    type: str = "string"
    required: bool = False
    #: The CLASS URI of what this slot's value names. DECLARED, never sniffed from an ``_id``
    #: suffix: the cost of guessing was measured — a filler emitted a plausible value at 0.92
    #: confidence and the engine answered an honest 422 to a perfectly answerable question.
    referent: Optional[str] = None
    values: Optional[list[str]] = None
    default: Optional[Any] = None
    #: WHICH OTHER SLOTS OF THIS ROW RESTRICT THIS SLOT'S VALID VALUES. Declared, because
    #: nothing in a provider's silence tells a scoping dimension from an ordinary bound value:
    #: `lot` genuinely restricts which rate vintages are valid, `direction: upstream` restricts
    #: nothing, and a gateway that treats every bound slot as scoping refuses menus that were
    #: always right — a worse defect than the one it fixes, because it fires on working paths.
    #:
    #: THE INVARIANT, AND IT IS THE OTHER HALF OF
    #: :attr:`iagent_mesh.enumeration.EnumerateInstancesResponse.scoped_by`:
    #:
    #:     scoped_by  <=  narrowed_by  &  bound
    #:
    #: A provider's `scoped_by` is DRAWN FROM this list, intersected with what is actually bound
    #: this turn. This side is the OBLIGATION, stated once at ratification; that side is the
    #: provider's CLAIM about one answer. A name here that never appears there is a narrowing
    #: nobody applied — the menu is refused. A name there that is not here is a provider
    #: claiming a scoping this row never declared, which is out of the invariant in the other
    #: direction and is a provider defect, not a row one.
    #:
    #: OPTIONAL AND `None`-DEFAULTED ON PURPOSE. `ref_basis` dumps slots with
    #: `exclude_none=True`, so an undeclared slot carries nothing into the hash and EVERY
    #: EXISTING `manifest_ref` IS UNCHANGED by this field's arrival. A `= []` default would put
    #: `narrowed_by: []` on every slot of every row and move every ref in the fleet, including
    #: rows that have nothing to do with menus. Measured, not assumed.
    narrowed_by: Optional[list[str]] = None

    @model_validator(mode="after")
    def _referent_only_on_spoken(self) -> "SlotDecl":
        if self.referent and self.kind not in ("spoken-mandatory", "spoken-optional"):
            raise ValueError(
                f"slot {self.name!r}: a referent belongs on a SPOKEN slot. A handle is resolved "
                f"by the dispatcher from the store and was never something a speaker names."
            )
        return self

    @model_validator(mode="after")
    def _narrowed_by_is_well_formed(self) -> "SlotDecl":
        if self.narrowed_by is None:
            return self
        if not self.narrowed_by:
            raise ValueError(
                f"slot {self.name!r}: narrowed_by is present but empty. An empty list and an "
                f"absent one would mean the same thing while looking like a decision — omit it."
            )
        for other in self.narrowed_by:
            if not other or not other.strip():
                raise ValueError(
                    f"slot {self.name!r}: narrowed_by carries a blank slot name, which claims "
                    f"a scoping nobody can check"
                )
        if len(set(self.narrowed_by)) != len(self.narrowed_by):
            raise ValueError(f"slot {self.name!r}: narrowed_by repeats a slot name")
        if self.name in self.narrowed_by:
            raise ValueError(
                f"slot {self.name!r}: a slot cannot be narrowed by itself — the menu would be "
                f"gated on the value it exists to choose"
            )
        # The CARRIER must be spoken, same reasoning as `referent` above: a menu is drawn for
        # somebody to pick from, and a handle is resolved by the dispatcher rather than picked.
        # A narrowing declared on a handle is inert, and an inert declaration that looks live is
        # the defect this field exists to prevent. The slots NAMED may be of any kind — a handle
        # the dispatcher bound can legitimately scope what a speaker is then offered.
        if self.kind not in ("spoken-mandatory", "spoken-optional"):
            raise ValueError(
                f"slot {self.name!r}: narrowed_by belongs on a SPOKEN slot. Nothing draws a "
                f"menu for a {self.kind} slot, so the declaration could never fire."
            )
        return self


class GraphManifest(BaseModel):
    """One ratified row. One row, one registered mesh verb."""

    model_config = ConfigDict(extra="forbid")

    graph_id: str
    #: Import path and the callable that BUILDS the graph — not a compiled graph. The host
    #: compiles it, so the checkpointer decision below is the host's to honour rather than the
    #: module's to make: a module that compiled itself could attach a checkpointer this row
    #: says is off.
    module: str
    builder: str = "build"

    #: --- the mesh verb this row registers ---------------------------------------------------
    verb: str
    name: str
    description: str
    input_uri: str
    output_uri: str
    owner_persona: Optional[str] = None
    domains: list[str] = Field(default_factory=list)
    cost_class: Literal["low", "medium", "high"] = "medium"
    requires_human_approval: bool = False
    timeout_s: Optional[float] = None
    synonyms: list[str] = Field(default_factory=list)
    anti_synonyms: list[str] = Field(default_factory=list)

    #: --- the contract -----------------------------------------------------------------------
    slots: list[SlotDecl] = Field(default_factory=list)
    #: ``single`` means the question must name one instance. Without arity the eligibility gate
    #: cannot drop a single-shaped verb from a set-shaped question, and the question routes to a
    #: verb that cannot answer it and 400s two hops later.
    arity: Optional[Literal["single", "set"]] = None
    refusal: Literal[REFUSAL_DISPOSITIONS] = "fail"  # type: ignore[valid-type]

    #: Per-graph and OFF by default. Durable per-thread memory that no node reads is storage
    #: cost with the appearance of statefulness — the defect that retired the exemplar this
    #: whole contract was first written against.
    checkpointer: bool = False

    @field_validator("verb")
    @classmethod
    def _verb_is_prefixed(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError(f"verb {v!r} must be a CURIE like 'mesh:finProgramBrief'")
        return v

    @field_validator("input_uri", "output_uri")
    @classmethod
    def _ends_are_absolute(cls, v: str) -> str:
        # Contract D refuses atomically if either end is absent, and a CURIE here reads at the
        # registrar as a MISSING class rather than a malformed one — a confusion that has cost
        # this ecosystem four separate diagnoses, the last of which lied convincingly.
        if not v.startswith("http"):
            raise ValueError(f"{v!r} must be an absolute class URI, not a CURIE")
        return v

    @model_validator(mode="after")
    def _arity_agrees_with_slots(self) -> "GraphManifest":
        forced = [s for s in self.slots
                  if s.required and s.referent and s.kind == "spoken-mandatory"]
        if forced and self.arity != "single":
            raise ValueError(
                f"{self.graph_id}: slot {forced[0].name!r} is both required and a referent, "
                f"which makes this verb single-instance — declare arity: single"
            )
        return self

    @model_validator(mode="after")
    def _no_untyped_passthrough(self) -> "GraphManifest":
        # REFUSED BY NAME. A `payload: object` slot is `run_any_graph` wearing a manifest: it
        # declares a verb whose input the router cannot reason about, cannot know is missing,
        # and cannot scope an entitlement to.
        for s in self.slots:
            if s.type in ("object", "any", "dict") or s.name in ("payload", "params", "body"):
                raise ValueError(
                    f"{self.graph_id}: slot {s.name!r} of type {s.type!r} is an untyped "
                    f"passthrough — ADR-0046 §2 refuses it. Declare the fields the graph reads."
                )
        return self

    @model_validator(mode="after")
    def _narrowed_by_names_resolve(self) -> "GraphManifest":
        # A NAME THAT MATCHES NOTHING IS THE SILENT FAILURE. `narrowed_by: ["Lot"]` against a
        # slot called `lot` never appears in any provider's `scoped_by`, so the gateway refuses
        # that menu FOREVER and the row looks correct. SlotDecl cannot catch it — it cannot see
        # its siblings — so the check belongs here, where the population is.
        known = {s.name for s in self.slots}
        for s in self.slots:
            for other in s.narrowed_by or ():
                if other not in known:
                    raise ValueError(
                        f"{self.graph_id}: slot {s.name!r} declares narrowed_by {other!r}, "
                        f"which is not a slot of this row. Known slots: "
                        f"{sorted(known)}"
                    )
        return self


def manifest_ref(m: GraphManifest) -> str:
    """``<graph_id>@<first 12 hex of sha256>`` over SEMANTIC content.

    Follows ``ruleset_ref``'s discipline so refs read alike in a record, and canonicalises the
    way ``cost_agent/export.py`` does — ``sort_keys=True`` with the separators PINNED, which is
    the one thing other implementations of this in the ecosystem lack. An unpinned separator is
    a ref that moves when a serializer's defaults do.

    The hash covers the CONTRACT — verb, both Contract D ends, slots, arity, refusal — not the
    file bytes. A reflowed comment or a reordered key does not mint a new ref; a changed slot
    does. Inherited cost, stated: the ref says "THIS contract" and nothing about the graph's
    code, so a module rewritten behind an unchanged contract keeps its ref.
    """
    blob = json.dumps(ref_basis(m), sort_keys=True, separators=(",", ":"))
    return f"{m.graph_id}@{hashlib.sha256(blob.encode()).hexdigest()[:12]}"


#: Fields of GraphManifest deliberately OUTSIDE the ref, each with the reason. A field added to
#: the model must be placed in the basis or in here, and `test_every_model_field_is_classified`
#: fails until it is — because the alternative is what happened: the ref quietly not covering
#: `referent` while a test varying two fields read as asserting the whole contract.
REF_COSMETIC: dict[str, str] = {
    "module": "where the code lives. A module rewritten behind an unchanged contract keeps its "
              "ref, by design — the ref says THIS CONTRACT and nothing about the implementation.",
    "builder": "same reason as module: the entry point is implementation, not contract.",
    "name": "the registration name. Derived from the row for the registrar's idempotency key; "
            "renaming it does not change what the verb accepts or produces.",
    "description": "prose. Retrieval input, not contract — and a reflowed sentence minting a new "
                   "ref is the churn `ruleset_ref`'s content-only property exists to avoid.",
    "synonyms": "routing hints. They change which questions REACH the verb, not what it is.",
    "anti_synonyms": "as synonyms.",
    "owner_persona": "who owns it operationally.",
    "domains": "entitlement scope, enforced at the gate rather than by the contract's identity.",
    "cost_class": "an operational hint to the dispatcher.",
    "requires_human_approval": "a dispatch-time policy, not part of the verb's shape.",
    "timeout_s": "an operational bound.",
    "checkpointer": "a HOSTING decision. Two hosts may run the same contract with and without "
                    "durable memory; the answer's shape is identical either way.",
}


def ref_basis(m: GraphManifest) -> dict:
    """The exact structure `manifest_ref` hashes. PUBLIC so it can be asserted against.

    Named and exported deliberately: the ref's coverage was previously implicit in a dict
    literal inside `manifest_ref`, and the seal for it varied `required` and `arity` and never
    `referent` — so it asserted the property for two fields and was read as asserting it for
    the contract. **A list grows when someone remembers; a derivation grows when the basis
    does.** Tests derive the covered fields from here.

    Slots go through `model_dump(exclude_none=True)`, so EVERY declared SlotDecl field is
    covered without being named here — including `referent`, whose omission was the gap.
    """
    return {
        "graph_id": m.graph_id,
        "verb": m.verb,
        "input_uri": m.input_uri,
        "output_uri": m.output_uri,
        "arity": m.arity,
        "refusal": m.refusal,
        "slots": [s.model_dump(exclude_none=True) for s in m.slots],
    }


def _read_rows(directory: Path) -> dict[str, tuple[Path, dict]]:
    """Raw YAML by graph_id, before validation, so a tombstone can be seen for what it is."""
    import yaml

    rows: dict[str, tuple[Path, dict]] = {}
    for f in sorted(Path(directory).glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        if raw is None:
            raise ManifestError(f"{f.name} is empty — an empty ratified row is not a row")
        gid = raw.get("graph_id")
        if not gid:
            raise ManifestError(f"{f.name} has no graph_id")
        if gid in rows:
            raise ManifestError(
                f"{f.name} and {rows[gid][0].name} both declare graph_id {gid!r}"
            )
        rows[gid] = (f, raw)
    return rows


def _build(fname: str, raw: dict) -> GraphManifest:
    try:
        return GraphManifest(**raw)
    except ManifestError:
        raise
    except Exception as exc:
        raise ManifestError(f"{fname} is not a valid graph manifest: {exc}") from exc


def load_manifests(directory: Path | str) -> list[GraphManifest]:
    """Every ratified row in one directory, validated, sorted by graph_id.

    RAISES on an invalid row rather than skipping it. A host that skipped one would come up
    healthy, serve every probe, and be missing exactly one verb — the failure mode with no
    symptom.
    """
    rows = _read_rows(Path(directory))
    out = []
    for gid in sorted(rows):
        f, raw = rows[gid]
        if raw.get("deleted"):
            raise ManifestError(
                f"{f.name} is a tombstone (deleted: true) but this is not an overlay — "
                f"a tombstone only means something composed against a seed. Delete the file."
            )
        out.append(_build(f.name, raw))
    _no_two_graphs_one_verb(out)
    return out


def compose(seed_dir: Path | str, overlay_dirs: Iterable[Path | str] = ()) -> list[GraphManifest]:
    """ADR-0036 composition: overlay entries REPLACE or DELETE by key; seed applies where the
    overlay is silent. Per-entry granularity, which is what makes deletion natural.

    An overlay row is a full replacement, not a field-level merge. ADR-0036 leaves field-level
    merge for "a real overlay [that] shows whether it is ever wanted", and adding it early would
    mean a customer's row silently inheriting a seed field they never read.

    A TOMBSTONE FOR A GRAPH THAT IS NOT IN THE SEED IS AN ERROR, not a no-op. A stale tombstone
    is how an overlay rots: the seed graph it deleted was renamed, the overlay keeps deleting a
    key nobody ships, and the graph the customer thought they had removed is registered again
    under the new name with nothing to say so.
    """
    rows = _read_rows(Path(seed_dir))
    for od in overlay_dirs:
        for gid, (f, raw) in _read_rows(Path(od)).items():
            if raw.get("deleted"):
                if gid not in rows:
                    raise ManifestError(
                        f"{f.name} deletes graph_id {gid!r}, which the seed does not ship. "
                        f"A tombstone for a graph that is not there silently stops deleting "
                        f"anything the day the seed renames it."
                    )
                rows.pop(gid)
            else:
                rows[gid] = (f, raw)
    out = [_build(rows[g][0].name, rows[g][1]) for g in sorted(rows)]
    _no_two_graphs_one_verb(out)
    return out


def _no_two_graphs_one_verb(ms: list[GraphManifest]) -> None:
    verbs = [m.verb for m in ms]
    dupes = sorted({v for v in verbs if verbs.count(v) > 1})
    if dupes:
        # ONE NAME PER (VERB, SUBJECT). The registrar's compensate-on-rescope sweep DELETES
        # rows matching (tool_urn, verb_iri) whose input_uri differs, so two rows sharing a verb
        # replace each other silently rather than both registering.
        raise ManifestError(f"two graphs registering the same verb: {dupes}")


def validate_dir(directory: Path | str) -> list[GraphManifest]:
    """The callable BOTH rails import — the policy repo's PR gate and the seed cronjob.

    Deliberately the same function rather than two that agree, because two that agree is a
    copy, and a copy drifts until a row passes one gate and fails the other.
    """
    return load_manifests(directory)


def json_schema() -> dict:
    """The source of the committed schema artifact. The models and the schema cannot disagree
    because one is generated from the other."""
    return GraphManifest.model_json_schema()


def registration_payload(m: GraphManifest, *, endpoint_url: str, version: str = "0.1.0") -> dict:
    """A ratified row rendered as the mesh registrar's ``RegistrationManifest`` body.

    PURE, and separated from the transport on purpose: this is the half a test can assert
    against without a registrar, and the half route C needs if it POSTs through its own client.
    """
    return {
        "name": m.name,
        "verb_iri": m.verb,
        "input_uri": m.input_uri,
        "output_uri": m.output_uri,
        "endpoint_url": endpoint_url,
        "description": m.description,
        "verb_synonyms": list(m.synonyms),
        "verb_anti_synonyms": list(m.anti_synonyms),
        "owner_persona": m.owner_persona,
        "domains": list(m.domains),
        "cost_class": m.cost_class,
        "requires_human_approval": m.requires_human_approval,
        "version": version,
        "timeout_s": m.timeout_s,
        "slots": [s.model_dump(exclude_none=True) for s in m.slots],
        "arity": m.arity,
        "required_args": [s.name for s in m.slots if s.required],
        "mesh_graph_ref": manifest_ref(m),
    }


class RefusalViolation(ValueError):
    """A graph's output contradicts the refusal disposition its ratified row declares."""


def enforce_refusal(m: GraphManifest, out: Any) -> Any:
    """Check a graph's output against its row's `refusal`. Returns `out`, or RAISES.

    ── WHY THIS IS IN THE SDK AND NOT IN ONE HOST ──────────────────────────────────────────
    It was implemented in the platform's own host first, on the ruling that the host holds both
    the row and the output. That is right and it is not sufficient: **a convention only one host
    implements is one route C will not inherit.** A team running their own host imports the same
    loader and the same schema; it must be able to import the same enforcement, or its rows
    declare a clause nothing checks — which is exactly the defect this closes.

    ── `holes` IS PART OF THE OUTPUT CONTRACT, STATED ──────────────────────────────────────
    A host cannot know how many findings a given graph SHOULD produce — that is domain
    knowledge it does not have. But a graph that reports a HOLE has told the host it narrowed
    its answer, and that is generic. So the one enforceable rule:

        refusal: named-hole   holes are the declared disposition — returned unchanged
        refusal: fail         a hole is a CONTRACT VIOLATION — raises

    A compliant `fail` graph raises at the refusal and never reaches here. A non-compliant one
    returns partials, and before this existed nothing anywhere went red: the row described
    behaviour it did not constrain.

    The error names the row's clause AND which holes caused it, and says it is a DISAGREEMENT
    between a row and its module rather than a runtime fault — because the fix is to change one
    of the two, and the reader needs to know which.
    """
    if m.refusal != "fail":
        return out
    holes = out.get("holes") if isinstance(out, dict) else None
    if holes:
        sources = [h.get("source", "?") for h in holes if isinstance(h, dict)]
        raise RefusalViolation(
            f"{m.graph_id} declares refusal=fail and returned {len(holes)} hole(s) "
            f"({', '.join(sources)}). Its row says a partial answer is not an answer for this "
            f"verb, so the output must NOT reach a caller who would read it as whole. Either "
            f"the module should have failed at the refusal, or the row should declare "
            f"named-hole — this is a contract disagreement between them, not a runtime error."
        )
    return out


def register_graph(
    m: GraphManifest,
    *,
    registrar_url: str,
    endpoint_url: str,
    mint: Optional[Callable[[], str]] = None,
    component: str = "graph-host",
    version: str = "0.1.0",
    timeout: float = 30.0,
):
    """Register one ratified row as a mesh verb. Returns the transport's RegistrationResult.

    One helper for both routes: our host calls it per composed row at boot, and a team running
    their own host calls it with their own ``endpoint_url``. Identity is an ARGUMENT — ``mint``
    is passed, never read from ambient env here — which is the rule that stopped a supervisor
    from dispatching as the review starter.
    """
    from .registration_transport import register_with_mesh

    return register_with_mesh(
        registrar_url,
        registration_payload(m, endpoint_url=endpoint_url, version=version),
        component=component,
        mint=mint,
        timeout=timeout,
    )
