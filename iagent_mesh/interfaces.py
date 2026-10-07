"""The mesh has one client: named operations that carry the caller and record what they read.

An engine sees the substrate through these Protocols and never through a query language or a
connection string. This is ADR-0049's bypass rule generalised from *"do not read the graph
directly"* to **"do not hold a driver at all"** — and it is ``run_any_graph`` for stores: a
Cypher or SPARQL slot is arbitrary code in a query's clothes.

── THE SDK OWNS INTERFACES AND IMPORTS NO IMPLEMENTATION AND NO DRIVER ─────────────────────
Nothing here imports ``neo4j``, ``weaviate-client``, ``rdflib`` or ``httpx``. A Protocol that
imported its implementation would make the dependency real however the module is named — R-038's
rule, and there is a seal asserting it rather than a comment claiming it.

**Enforcement of the ban is NOT here and is not a name list.** Three findings drove that and each
defeats a name-based instrument on its own — *the import name is not the capability* (``rdflib``
parses local Turtle and is not a driver), *the pyproject is not the import*
(``agent_fleet/utils/`` has no pyproject and three engines import it), and *the import is not the
connection* (Jena is reached by raw ``httpx``; Weaviate by ``urllib.request``, which ships with
Python and can never be banned). Those three stand: a name list cannot enforce this ban.

⚠ **WHAT ENFORCES IT TODAY IS NOT WHAT THIS DOCSTRING USED TO CLAIM.** It said *"It is a
NetworkPolicy"* — present tense, a control that **does not exist**. Measured 2026-09-16: the chart
carries no NetworkPolicy template and the string appears nowhere in it. That is the same absent
control the allowlist seal cited, and a docstring asserting enforcement that is not deployed is
worse than one that asserts nothing: an implementer reads this file and concludes the perimeter
holds, so the claim **removes** the scrutiny the gap needs.

The honest statement:

- a NetworkPolicy is the INTENDED enforcement — a pod that cannot route to the store cannot
  reach it whatever it imports, which is the only instrument the three findings do not defeat;
- **none exists as of 2026-09-16**;
- until one does, the ban rests on the **substrate-address lint** and the **import seal** — both
  real, both weaker than a route-level control, and neither reaching the ``urllib.request`` case
  the third finding names;
- the gap is carried as a **strict xfail**, so the day the policy lands that arm goes XPASS and
  **forces this paragraph to be rewritten** rather than leaving a stale denial behind a shipped
  control.

── THE OPERATIONS ARE DERIVED, NOT DESIGNED ────────────────────────────────────────────────
Every method below comes from the engine-o read inventory — a census of what direct substrate
accesses were TRYING TO DO, not a table of what an interface ought to offer. The inventory's own
count is the authority: nine Neo4j reads and **zero Neo4j writes**, two Weaviate searches and one
existence probe, five Jena operations of which one is the executor rather than an operation on it.

── THREE PROPERTIES EVERY INTERFACE SHARES ─────────────────────────────────────────────────
1. **Identity is an argument.** Every operation takes the :class:`Initiator`. A service identity
   is refused at the boundary.
2. **Every read records what was read** — the dataset URN, the graph IRIs, the collection —
   from the abstraction, not from an engine remembering to.
3. **Named operations only.** New capability is a new operation with a manifest and a seal, the
   same discipline as a verb, never a wider query surface.

Only the first is checkable offline. The second needs a real write and lives in the live arm.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .results import MeshResult
from .write_results import MeshWriteResult

__all__ = [
    "Initiator",
    "ServiceIdentityRefused",
    "DelegateIdentityRefused",
    "MeshGraph",
    "MeshOntology",
    "MeshVectors",
    "MESH_COLLECTION_META",
    "CollectionMarker",
    "CorruptCollectionMarker",
    "collection_marker",
    "read_collection_marker",
    "marker_predates_collection",
    "marker_is_stale",  # DEPRECATED alias; removed once in-fleet callers move
    "MARKER_ASSERTS",
    "MARKER_DOES_NOT_ASSERT",
    "Embedder",
    "EdgeIdentity",
    "EdgeIdentityFilter",
    "MeshGraphWriter",
    "MeshVectorsWriter",
    "MeshOntologyWriter",
]


class ServiceIdentityRefused(PermissionError):
    """A service identity reached an operation that requires an initiator.

    Not a generic authz error on purpose: this names the ONE condition, so a caller reading the
    raise learns the rule rather than that something was denied.
    """


class DelegateIdentityRefused(PermissionError):
    """A delegate identity reached an operation that requires a person.

    A delegate acts under ITS OWN grants — ``Initiator.on_behalf_of`` names who it is
    accountable to, and is never a gate input (see the field's docstring). This names the
    boundary the same way ``ServiceIdentityRefused`` names its own, rather than making a caller
    catch the older exception and wonder whether "service" now means both.
    """


class Initiator(BaseModel):
    """Who is asking. Carried, never parsed.

    **``kind`` IS DECLARED, NOT SNIFFED, and that is load-bearing.** The rule is "a service
    identity is refused at the boundary", and the obvious implementation — inspect the subject
    for a ``svc:`` prefix or a ``service-account-`` shape — would violate the older and stronger
    rule that **identity is carried opaque and nothing parses its format**. Subject spellings
    differ per deployment (an email in one, an employee id in another, a Keycloak service-account
    name in a third); a parser that works in sandbox mislabels at work, and it mislabels
    SILENTLY because both readings produce a plausible identity.

    So the classification comes from the token's claims at the edge that minted it, and travels
    here as a declared field. ``subject`` is an opaque string this SDK never interprets.

    **NOT A CONTRADICTION WITH THE GRANT RAIL, and this is where the next person will look.**
    The policy validator DOES refuse a ``svc:`` prefix in a disclosure grant, and that is a
    different thing: there the spelling is OURS — a declaration's format on the git rail, written
    by us, reviewed by us, and therefore ours to constrain. Here the subject arrives from a token
    minted elsewhere, and constraining ITS format is asserting a fact about someone else's issuer.
    **Same-looking rule, opposite direction of authority.** Conflating them is how the prefix
    check gets re-implemented on the wrong side.

    **``"delegate"`` (added 2026-09-27) is a THIRD kind, not a spelling of ``"service"``.** It is
    a non-human session (a lane worktree, a scheduled job run under someone's authority) acting
    under its OWN entitlements — distinct from a deployed service, which has none it can be asked
    about, and from a person, whose grants it must not silently inherit. ``on_behalf_of`` carries
    who it is accountable to; that field is provenance, never a gate input, for the same reason
    ``authz_id`` and a provenance actor are kept as separate fields elsewhere in this system.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    """The authorization identity, opaque. Whatever claim the deployment keys on."""

    kind: Literal["person", "service", "delegate"]

    on_behalf_of: Optional[str] = None
    """Who a DELEGATE is accountable to. Opaque, same discipline as ``subject`` — never parsed.

    **PROVENANCE, NOT A GATE INPUT.** No guard in this SDK reads it, and none should: a delegate's
    admission is decided by its OWN grants (``subject``), and letting ``on_behalf_of`` change an
    authorization outcome would be the authz-subject/provenance-actor collapse this field exists
    to avoid — attribution and permission are different questions that happen to share a value.

    Required, non-blank, when ``kind == "delegate"`` — a delegate with nobody accountable is a
    service wearing a different label. Refused (must be ``None``) otherwise: setting it on a
    person or a service asserts a relationship neither kind declares.
    """

    @field_validator("subject")
    @classmethod
    def _subject_is_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "initiator subject is empty — an anonymous read is not a read with a missing "
                "name, it is a read nobody can be held to"
            )
        return v

    @model_validator(mode="after")
    def _on_behalf_of_matches_kind(self) -> "Initiator":
        if self.kind == "delegate":
            if self.on_behalf_of is None or not self.on_behalf_of.strip():
                raise ValueError(
                    "a delegate initiator must name who it acts for in on_behalf_of — a "
                    "delegate with nobody accountable is a service under another name"
                )
        elif self.on_behalf_of is not None:
            raise ValueError(
                f"on_behalf_of is set ({self.on_behalf_of!r}) but kind={self.kind!r} is not "
                "'delegate' — the field exists only to name who a delegate acts for, and "
                "setting it on a person or a service asserts a relationship that kind never "
                "declared"
            )
        return self

    def require_person(self, operation: str) -> "Initiator":
        """Refuse anything that is not a person, naming the operation. The boundary check, one call.

        **AN ALLOWLIST, NOT A DENYLIST — ruled 2026-09-27, the day ``kind`` grew a third value.**
        The old body read ``if self.kind == "service": raise`` — a comparison that ADMITS
        anything it does not name. Widening ``kind`` to add ``"delegate"`` without touching that
        line would have let a delegate straight through every operation this check exists to
        gate, silently, which is the one failure a boundary check must never have. ``kind !=
        "person"`` cannot make that mistake again: a fourth kind, whenever one is declared, is
        refused by construction rather than by whoever remembers to update every call site.

        The same comparison was copied into the fleet twice (``ontology_service/mesh_graph.py``,
        ``mesh_vectors.py``) — this is the shared import those two copies should become, so the
        allowlist is written once rather than kept in sync by hand three times.
        """
        if self.kind == "person":
            return self
        if self.kind == "delegate":
            raise DelegateIdentityRefused(
                f"{operation} requires a person and received a delegate identity "
                f"({self.subject!r}, acting for {self.on_behalf_of!r}). A delegate's own grants "
                "govern what it may invoke; this operation is not one of them."
            )
        raise ServiceIdentityRefused(
            f"{operation} requires an initiator and received a service identity "
            f"({self.subject!r}). A read attributed to a service records provenance no "
            f"person can be asked about."
        )

    def require_person_or_delegate(self, operation: str) -> "Initiator":
        """Refuse a bare service; admit a person or a delegate. THE WRITE BOUNDARY, ruled
        2026-09-27 alongside ``kind`` growing its third value — a WIDER allowlist than
        :meth:`require_person`, not a replacement for it.

        Reads keep the narrower gate: `require_person` stays person-only, unchanged. Writes admit
        a delegate too, because the shape ``"delegate"`` was added FOR — a lane worktree, a
        scheduled job run under someone's own authority — legitimately writes on its own
        entitlements. What it may never do is inherit a person's grants silently, and it does
        not: a delegate is admitted here on its OWN ``subject``, exactly as a person is, and
        ``on_behalf_of`` is recorded, never consulted — the same PROVENANCE-NOT-A-GATE-INPUT
        discipline the field's own docstring states, now exercised at a real boundary instead of
        only declared at one.

        A bare SERVICE is refused for the same reason it is refused on the read side, with MORE
        force rather than less: a write attributed to a service records a state change nobody can
        be asked about, where a read attributed to one only records a query nobody can be asked
        about.

        No new exception for "delegate refused" — there is nothing left for a delegate to be
        refused FOR at this boundary. The line this method draws is person-or-delegate versus
        service, so a delegate never reaches the branch that would raise
        ``DelegateIdentityRefused``; that exception stays scoped to `require_person`, where a
        delegate genuinely is the refused case.
        """
        if self.kind in ("person", "delegate"):
            return self
        raise ServiceIdentityRefused(
            f"{operation} requires a person or a delegate and received a service identity "
            f"({self.subject!r}). A write attributed to a service records a state change no "
            f"person can be asked about."
        )


# ── the three interfaces ─────────────────────────────────────────────────────────────────


@runtime_checkable
class MeshGraph(Protocol):
    """Named reads over the property graph. **READ-ONLY, and that is ruled, not an omission.**

    The inventory found **zero Neo4j writes** in engine-o — the engine that holds the driver —
    because the writer is the registrar and state writes go through the mesh writer with
    ``DERIVED_FROM``. A write half added "for symmetry" would mint a surface whose only caller
    does not exist, which is ``run_any_graph`` reasoning applied to shape rather than to
    arbitrariness.
    """

    #: This interface answers one way, so its results carry no mode. Declared rather than
    #: omitted: a consumer can tell "no mode exists here" from "the implementation forgot".
    MODES: tuple[str, ...] = ()

    def registry(self, initiator: Initiator) -> MeshResult:
        """Which personas and domains are active."""

    def providers_for(self, initiator: Initiator, verb: str) -> MeshResult:
        """Engines registered as providers of ``verb``.

        THREE STATES, OF WHICH ONLY TWO ARE CACHEABLE: registered, none-registered (a checked
        answer) and unknown. **``unreachable`` must never be cached** — one blip would silence
        enumeration for a whole TTL, which is how a failed lookup came to render as "no provider
        is registered".
        """

    def classes_with_a_verb(
        self, initiator: Initiator, domains: Sequence[str], *, include_referents: bool = False
    ) -> MeshResult:
        """Classes carrying a verb in these domains — the productive-option gate.

        ITS CALLER DEGRADES OPEN, DELIBERATELY: an empty means *do not filter*, because failing
        closed empties the candidate pool and takes routing down globally. That disposition is
        the CALLER'S and is written at the call site — this operation still reports ``failed``
        honestly. An exemption from the result type would hide the one decision worth showing.
        """

    def data_assets_for(self, initiator: Initiator, iri: str) -> MeshResult:
        """Physical dataset URNs behind an ontology IRI."""

    def edge(self, initiator: Initiator, subject: str, verb: str) -> MeshResult:
        """Resolve one predicate edge, cheapest by cost class."""

    def path(
        self, initiator: Initiator, start: str, end: str, *, cost_classes: Sequence[str]
    ) -> MeshResult:
        """Shortest composition from ``start`` to ``end`` within the allowed cost classes."""

    def operable_subjects(self, initiator: Initiator, domain: str) -> MeshResult:
        """Classes carrying at least one registered verb, domain-scoped and visibility-filtered.

        Filtered for THIS initiator — which is why identity is an argument rather than ambient.
        """

    def verbs_for(self, initiator: Initiator, subject: str, *, max_hops: int) -> MeshResult:
        """Predicates that can operate on ``subject``, walking the ancestor chain.

        **ROW SHAPE WIDENED, 2026-10-02** — closing the gap ia-74 routed: "the Protocol declares
        no row shape... it returns 4 fields, the route returns 14." The richer row
        (``ontology_service``'s ``/find_compatible_verbs`` — "the route") is now this method's
        declared shape, not a narrower one some implementations happen to answer with:

        | field | meaning |
        |---|---|
        | ``verb_iri`` | the predicate's full IRI |
        | ``verb_local`` | the predicate's local name. **Renamed from this SDK's prior ``verb_type``** — one fact, one name; an implementation widening to this shape renames the field, it does not carry both |
        | ``input_uri`` | the class this verb's input must satisfy |
        | ``output_uri`` | the class this verb's output satisfies |
        | ``endpoint_url`` | where the verb is registered to be called, or ``None`` |
        | ``owner_persona`` | the persona that registered it, or ``None`` |
        | ``domains`` | the domains it is scoped to; empty means domain-agnostic |
        | ``cost_class`` | its registered cost class, or ``None`` |
        | ``requires_human_approval`` | declared at registration, never inferred |
        | ``hops`` | ancestor-chain distance from ``subject`` to the class that admitted this verb |
        | ``compatibility`` | which rule admitted it — ``"subject"`` (operates on ``subject`` directly) today; a non-``"subject"`` value is reserved, not yet produced by this leg |
        | ``slots`` | the verb's declared slot requirements, as the JSON string the route already carries them in — not decoded here |
        | ``arity`` | declared input cardinality (``"single"``/``"set"``/``"any"``), or ``None`` |
        | ``required_args`` | declared argument keys the verb cannot run without; empty means unconstrained |

        **Scope of this widening, stated so it is not assumed wider than it is:** this is the ROW
        shape only. ``verbs_for`` still walks exactly the ancestor chain it always has — what
        ia-74 named LEG 1 (coverage). It does **not** add LEG 2 (a verb admitted because a
        *referent* slot covers ``subject``, not ``subject`` itself) or LEG 3 (the universal
        referent set, every subject's ``mesh:explain``), and it takes no new parameter for either.
        Those stay future, unscoped work — ia-74's report measured LEG 2 adding verbs on 4 of
        1070 subjects and found LEG 3 dead by construction (a service identity cannot reach it;
        a design question for a person, not a lane fix), and today's order rules the row's shape,
        not the walk's reach. A ``compatibility`` value other than ``"subject"`` is reserved for
        whenever that ruling lands, not produced by this leg now.

        No conformance arm exists yet for this method, or for any ``MeshGraph`` read — unlike
        ``MeshGraphWriter``, this Protocol has none today. Widening the row shape does not open
        one; that is a separate, larger undertaking this order does not ask for.
        """

    def ancestors(self, initiator: Initiator, iri: str, *, max_hops: int) -> MeshResult:
        """The ``subClassOf`` chain.

        REFUSES RATHER THAN DEGRADING: a failed ancestor walk silently narrows verb
        compatibility and returns classification to pre-ADR-0018 behaviour, and a degraded answer
        there is indistinguishable from a considered one.
        """


@runtime_checkable
class MeshOntology(Protocol):
    """Named reads over the RDF store. **NO WRITE HALF TODAY — the earlier blocker stated here was
    FALSE, corrected 2026-09-27.** Measured by ``doc-tools/lane/7f`` against sandbox Fuseki:
    ``doc-tools/sessions/2026-09-27-report-7f-mesh-jena-update-route-and-writer-inventory.md``.

    **The route works.** ``POST update=<sparql>`` to ``{fusekiUrl}/ds/update`` returns 200
    ("Update succeeded"). Both engine-o (reads a declared ``JENA_UPDATE_ENDPOINT``) and doc-tools
    (concatenates ``{base_url}/{dataset}/update``) already reach the identical address by two
    different, non-derived constructions. **No live code performs an ``endpoint.replace("/sparql",
    "/update")`` substitution** — it was removed 2026-09-14 as a latent hazard, never an observed
    failure (``agent_fleet/ontology_service/substrate_posture.py:91-107``, "DECLARED, NEVER
    DERIVED"). This docstring had restated a removed hazard as a present-tense one, which is a
    worse thing for a docstring to do than say nothing: the next reader spends an evening
    re-measuring a bug that was fixed two weeks earlier.

    **THE GET-404 TRAP, named so nobody re-derives the false conclusion.** ``GET /ds/sparql``
    404s while a *posted* query against that same path returns 200 — Fuseki's query endpoint
    answers POST only. A route-existence check done with GET alone concludes the endpoint is
    absent. That is almost certainly how "no configured endpoint contains ``/sparql``" got written
    down here originally.

    **THE WRITE HALF NOW EXISTS — this paragraph is the second correction the same day forced,
    and it is being made the same way the first one was: named, not left standing.** Ruled
    2026-09-27 on
    ``invincible-agent/sessions/2026-09-27-proposal-from-ca-a-write-half-for-meshgraph-and-meshvectors.md``:
    see :class:`MeshOntologyWriter` below, and :mod:`iagent_mesh.writers.jena` for the reference
    implementation that closes the exact defect this docstring used to describe — doc-tools' own
    Jena writer inserting three of its four SPARQL-emitting plugins into Jena's *default* graph,
    invisible to the mesh resolver, because nothing at the write call forced scoping. The read
    Protocol below is UNCHANGED and stays pure: the write half is a sibling class, never a new
    method here, so this Protocol's own "read-only" framing keeps being true rather than needing
    a third correction later.
    """

    MODES: tuple[str, ...] = ()

    def ask(self, initiator: Initiator, *, iri: str, graph: Optional[str] = None) -> MeshResult:
        """Does this IRI (optionally within this graph) resolve?

        A boolean question, and it still returns the result type: ``empty`` means *asked, and it
        does not exist*, which is not the same as *could not ask*. Collapsing those is how a
        decision-record write came to be guarded by a check that could not fail.
        """

    def construct(self, initiator: Initiator, *, subject: str, graph: Optional[str] = None) -> MeshResult:
        """A typed subgraph as Turtle, term types intact.

        TYPES INTACT IS THE POINT: the SELECT executor drops them, so a typed read has to be a
        CONSTRUCT and parse rather than a SELECT and guess.
        """


#: THE MARKER COLLECTION. A carrier that is OURS BY CONSTRUCTION, ruled 2026-09-14 over an
#: encoding in ``description``. Every encoding into a human prose field creates the same three
#: choices and all three are traps: overwrite loses a sentence with nothing red, refuse turns a
#: check into the thing that gets muted, and splice is **a parser over a field that was never a
#: format**. A collection of our own has none of them.
MESH_COLLECTION_META = "MeshCollectionMeta"


class CorruptCollectionMarker(ValueError):
    """OUR marker exists and is not readable. NOT the same as absent: nobody-wrote-one is a gap,
    something-wrote-ours-badly is a failure, and they want opposite behaviours."""


class CollectionMarker(BaseModel):
    """What the writer records about a vector collection, and the reader checks at open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection: str

    model: str
    """**THE SERVED IDENTITY — what the endpoint SAID IT USED, not what we asked for and not a
    constant.** Measured in-cluster: an OpenAI-compatible embeddings response carries
    ``model`` in the same payload as the vector it describes, and the writer already makes that
    call and discards the field one line from where it is needed. Free, provider-neutral, and it
    catches the case NEITHER constant reaches — an endpoint quietly serving something other than
    what was requested.

    ⚠ A CONSEQUENCE WORTH EXPECTING: a collection written while the endpoint was misconfigured
    records the wrong model FAITHFULLY. That marker will disagree with both constants and will
    look like a bug — and it will be the only thing in the system telling the truth about what
    produced those vectors.

    The weaker readings, and why each is refused: a constant records what the code believes; ``LLM_EMBED_MODEL`` overrides the default at
    ``LLM_EMBED_MODEL`` overrides the default at runtime on both sides, so a writer that stamps its
    constant and a reader that compares its constant AGREE WITH EACH OTHER WHILE BOTH DISAGREE
    WITH THE VECTORS ON DISK. The resolved request value is better and still records an
    intention; only the response records an outcome."""

    version: Optional[str] = None
    """The model's version, **ABSENT WHERE NONE IS KNOWN — and absent is a STATE, not a value.**

    There is no version source in the writer's repo today: two constants, a model name and a
    dimension, and the embeddings response is never inspected for one. A DECLARED SENTINEL was
    the obvious alternative and is refused: a sentinel is still a string, ``marker.version ==
    mine.version`` matches it happily, and the contract can say a sentinel match is not evidence
    while the TYPE cannot enforce it. ``Optional`` enforces what prose cannot.

    **A comparison runs only when BOTH sides carry one.** Otherwise the version is reported
    UNVERIFIED — never silently agreed.

    **IF IT IS FILLED IT MUST BE AN IMMUTABLE IDENTITY — A DIGEST, NEVER A TAG.** Measured: the
    embeddings response carries no version at all, and the provider's own tag route returns
    ``nomic-embed-text:latest`` alongside a digest. **``:latest`` is a mutable pointer**; stamping
    it records a name that can point at different content tomorrow, which is the
    green-for-the-wrong-reason this field exists to avoid, wearing a version's clothes.

    **AND A DIGEST CANNOT BE A CONTRACT REQUIREMENT**, because the routes that expose one are
    provider-specific while the fleet configures an OpenAI-compatible base URL. Requiring it
    would bind this SDK to one provider — a worse coupling than the one being removed. So: an
    Ollama-backed writer MAY enrich this field, a LiteLLM-backed writer honestly reports absence,
    and **no implementation is ever forced to invent the field the marker exists to compare.**

    NOT ENFORCED IN CODE, DELIBERATELY: rejecting "a tag" would mean parsing a provider-specific
    string format, which is the same mistake as sniffing an identity's shape. The contract states
    it; a validator that guessed would be wrong in a deployment nobody here has seen."""

    dimension: int
    """THE OBSERVED VECTOR LENGTH, never a constant. Same reasoning as ``model``, and it buys a
    second independent witness: a stored vector's own length is checkable without any marker at
    all, so marker-says-N and vectors-are-N are two facts whose disagreement is detectable."""
    written_by: str
    """WHICH SIDE stamped it — the repo or service, not the asset. On a mismatch the reader's
    question is *which side changed*, and an asset name does not answer it."""

    collection_created_unix_ms: int
    """The collection's creation stamp AS THE WRITER OBSERVED IT — the anti-staleness handle.

    A marker in its own collection OUTLIVES the collection it describes, where a description died
    with it. Recreate `OntologyClass`, re-ingest, and a marker from the old one is a confident
    statement about vectors that no longer exist — a stale record reading exactly like a current
    one, which is the failure this whole mechanism exists to end. This field is what lets a
    reader detect that.
    """

    @field_validator("collection", "model", "written_by")
    @classmethod
    def _present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a collection marker needs every field; an empty one cannot "
                             "discriminate and a marker that cannot discriminate is not a marker")
        return v


def collection_marker(*, collection: str, model: str, dimension: int,
                      written_by: str, collection_created_unix_ms: int,
                      version: Optional[str] = None) -> dict:
    """What a WRITER stores, in the SAME ACT that creates the collection.

    **FOLD, NOT HAND-RUN** — the way the prime writes its own run row. A marker written by a
    separate step is a marker that can be forgotten, and a forgotten marker reads as ABSENT while
    the collection is perfectly real.

    ⚠ **A WRITER-SIDE REQUIREMENT THAT MUST BE DECLARED RATHER THAN DISCOVERED: on re-ingest the
    objects' creation times MUST move forward.** The staleness check below has no collection-level
    timestamp to use and proxies it with the oldest object's. If a writer ever PRESERVES the
    original object timestamps through a re-ingest, the proxy stops advancing while the vectors
    change underneath, and **the staleness check is silently defeated** — it keeps passing and
    means nothing.

    One implementation, so the writer and reader cannot diverge by agreeing on a shape separately.
    """
    marker = CollectionMarker(
        collection=collection, model=model, version=version, dimension=dimension,
        written_by=written_by, collection_created_unix_ms=collection_created_unix_ms,
    )
    return marker.model_dump()


def read_collection_marker(raw: Optional[dict]) -> Optional[CollectionMarker]:
    """``None`` means ABSENT — never "matches". A malformed marker RAISES."""
    if raw is None:
        return None
    try:
        return CollectionMarker(**raw)
    except Exception as exc:  # noqa: BLE001
        raise CorruptCollectionMarker(
            f"a {MESH_COLLECTION_META} marker exists and is not readable ({exc}). This is OUR "
            f"record damaged, not an absent one — refusing rather than opening"
        ) from exc


def marker_predates_collection(marker: CollectionMarker,
                               oldest_object_unix_ms: Optional[int]) -> bool:
    """Does this marker predate the collection it claims to describe?

    **NAMED FOR WHAT IT CAN ASSERT.** It was `marker_is_stale`, which names a CONCLUSION
    this predicate cannot reach: `stale` implies the marker is out of date with respect to
    the vectors, and what is actually computed is `absent-or-older-than-the-oldest-object`.
    Those differ exactly when the proxy is defeated, which is today (see below). A caveat
    leaves the wrong inference available and asks every reader to remember the correction;
    narrowing the NAME removes it. **A name is read; a docstring is not.**

    **MEASURED CONSTRAINT: a vector store here exposes NO collection-level creation timestamp** —
    the class schema carries nothing time-like. So the collection's age is proxied by its OLDEST
    OBJECT: a recreated-and-re-ingested collection has all-new objects, so its oldest is newer
    than a marker left behind by the old one.

    **AN EMPTY COLLECTION CANNOT BE DATED, AND THAT IS ABSENT RATHER THAN VALID.** With no object
    there is no proxy, and treating an undatable marker as current is exactly the confident-stale
    reading the field exists to prevent.

    ⚠⚠ **THIS PROXY IS ALREADY DEFEATED IN THE CURRENT FLEET — MEASURED, NOT PREDICTED, AND THIS
    FUNCTION MUST NOT BE RELIED ON UNTIL IT IS REPLACED.** The writer rewrites objects IN PLACE on
    deterministic UUIDs, and the store PRESERVES ``creationTimeUnix`` across a replace. Measured
    2026-09-15: 132 of 132 sampled `Predicate` objects carry an update time later than their
    creation time, the widest gap 81 days. So the oldest object's creation time **does not move
    while the vectors underneath are rewritten** — the proxy stops advancing exactly when it
    matters, and the check keeps passing and means nothing.

    It is shipped in this state DELIBERATELY AND DECLARED RATHER THAN QUIETLY: a known-broken
    check that says so is a gap with an owner; the same check shipped silent is the confident
    green this entire mechanism exists to end. **A conformance run may treat a non-stale verdict
    from this function as UNPROVEN, never as evidence of freshness.**

    THE REPLACEMENT UNDER RULING makes staleness UNREPRESENTABLE rather than detectable: refresh
    the marker in the same act that WRITES VECTORS, not only at creation. Then the code path that
    changes the vectors changes the marker, a marker describing vectors that no longer exist
    cannot be produced, and this function, its timestamp field and the empty-collection edge case
    all disappear together. The alternative — forbidding the writer to preserve creation times —
    abandons deterministic-uuid idempotency to keep an external measurement alive, which is the
    data model serving the instrument.
    """
    if oldest_object_unix_ms is None:
        return True
    return marker.collection_created_unix_ms < oldest_object_unix_ms


def marker_is_stale(marker: CollectionMarker, oldest_object_unix_ms: Optional[int]) -> bool:
    """DEPRECATED — the old name for :func:`marker_predates_collection`. Delegates.

    EXPAND/CONTRACT, NOT A CLEAN RENAME, and the reason is a live consumer: this name is public
    in 0.9.0 and 0.9.1 and another lane is building against it right now. Removing it in the same
    act that introduces the new name would break an importer to fix a wording — a rename needs a
    dual interval, the same rule as a grant key.

    The warning is the point: **a DeprecationWarning is READ AT RUNTIME, where a docstring is
    not.** It names the replacement and why the old name was wrong, so a caller who never opens
    this file still learns that `stale` was asserting more than the check can reach.

    CONTRACT: removed in the release AFTER every in-fleet caller moves. It is an interval, not a
    permanent alias — a permanent one would keep the misleading name readable, which is the whole
    thing the rename exists to stop.
    """
    import warnings

    warnings.warn(
        "marker_is_stale() is deprecated: the name asserts STALENESS, which this predicate "
        "cannot determine — it computes absent-or-older-than-the-oldest-object, and that proxy "
        "is currently defeated by the store preserving creationTimeUnix across a replace. Use "
        "marker_predates_collection(), which is named for what it can assert. FRESHNESS IS NOT "
        "ASSERTED BY THIS CONTRACT (see MARKER_DOES_NOT_ASSERT).",
        DeprecationWarning,
        stacklevel=2,
    )
    return marker_predates_collection(marker, oldest_object_unix_ms)


#: WHAT A MARKER CHECK ESTABLISHES, AS DATA RATHER THAN PROSE.
#:
#: The ruling: freshness is declared OUT OF SCOPE **in the contract**, not implied by a green and
#: not corrected in a docstring. These two tuples are that declaration — a reader (and a test)
#: can ask the contract what it asserts instead of inferring it from the absence of a failure.
#:
#: A passing `check_embedding_contract` means the collection's vectors were written by the model
#: and dimension declared — TWO WITNESSES — and says NOTHING about whether they are current.
MARKER_ASSERTS: tuple = ("model", "dimension")

#: Deliberately NOT asserted. `currency` is here because the only available proxy for it is
#: defeated by the substrate rather than by any choice a writer can make: the store preserves
#: `creationTimeUnix` across a replace-on-deterministic-UUID (measured: 132 of 132 Predicate
#: rows, widest gap 81 days). A property that cannot be established must be named as unasserted,
#: or its absence reads as its presence.
MARKER_DOES_NOT_ASSERT: tuple = ("currency",)


@runtime_checkable
class MeshVectors(Protocol):
    """Semantic lookup within a declared collection and domain.

    **THE EMBEDDING CONTRACT BELONGS TO THE IMPLEMENTATION, AND THE INTERFACE SAYS SO.** The
    vector is computed by the CALLER today — ``embed_query()`` to LiteLLM, handed to Weaviate as
    ``vector=`` — because Weaviate here is dumb storage with no text2vec module on the cluster
    side. So a bare ``nominate(text)`` would be a lie by omission: two implementations handed the
    same text can embed with two different models against one stored index, and nothing in the
    call would say so.

    :attr:`embedding_model` is therefore part of the contract, and conformance asserts an
    implementation verifies it against the collection before searching rather than after.
    """

    #: Declared per-interface, not centrally: a closed enum in the SDK would make every new mode
    #: an SDK release and put the vocabulary somewhere other than the interface that owns it.
    #: Conformance asserts an implementation emits ONLY these.
    MODES: tuple[str, ...] = ("hybrid", "bm25")

    @property
    def embedding_model(self) -> str:
        """The model this implementation embeds with. **Declared here; only PARTLY checkable.**

        ⚠ WHAT THE STORE RECORDS, measured against live Weaviate rather than assumed: both
        collections report ``vectorizer: None``, ``moduleConfig: {}`` and **no property recording
        a model**. The stored vector DIMENSION (768) is the only thing derivable. That follows
        from Weaviate being dumb storage here, but the consequence for this contract is the part
        worth stating: **there is nothing on the collection to compare a model name against.**

        So a conformance arm phrased *"verifies its model against the collection's"* would have
        exactly one way to be satisfied — **the implementation comparing its own constant to its
        own constant, and passing.** Green, vacuous, and indistinguishable from a real check: a
        legal input that makes two behaviours identical, arriving on the arm meant to prevent
        exactly that.

        **ASSERTED AT OPEN, NOT PER QUERY** (ruled 2026-09-14). Open is the one moment both
        sides pass through: a per-query check costs a round trip on every search **and still
        leaves the first WRITE unguarded**, and a write with the wrong model is as much the
        failure as a read. A mismatch at open is a REFUSAL NAMING BOTH.

        **THREE STATES, AND THE THIRD IS THE ONE THAT BITES.** The writer records the model's
        name and version as collection metadata at create-or-first-write; readers land before
        writers, so metadata is ABSENT for a while:

            matching      open
            mismatching   refuse, naming both
            absent        open, and REPORT THE GAP ONCE

        **Absent must never be silently treated as matching** — that is precisely the vacuous
        self-comparison this whole property was rewritten to avoid, and it would arrive looking
        like tolerance. A conformance suite exercising only the matching case cannot tell the
        assertion from its absence.

        Until metadata exists the only thing derivable is the stored DIMENSION, and it catches a
        model swap **only when the dimensions differ**: the fleet's own constant warns that
        vectors stored under an old model *"are not numerically compatible with vectors from a
        new model, even if the dimensions match"*. The silent case is the one that matters and
        the dimension does not reach it.

        **THE WRITER-SIDE HALF IS NOT THIS SDK'S TO MAKE** and is named with its owner: the
        collections are written by the doc-tools sync, readers only read, so no reading-side
        implementation can create what it needs to check against. A known gap with an owner
        rather than a vacuous green.

        *(The one-shared-constant framing was considered and rejected: making the two copies
        agree with each other still leaves nobody agreeing with the vectors already stored.)*
        """

    def nominate(
        self,
        initiator: Initiator,
        *,
        collection: str,
        text: str,
        domains: Sequence[str] = (),
        limit: int = 10,
        mode: Literal["vector_only", "hybrid"] = "vector_only",
        metadata_filters: Mapping[str, object] = MappingProxyType({}),
    ) -> MeshResult:
        """Candidate rows for a phrase, within one collection and across the given domains.

        ``domains`` IS A SEQUENCE AND THE SINGULAR FORM WOULD BE A REGRESSION. Both live call
        sites scope by a LIST, and the single-string parameter is the one that was SUPERSEDED
        (2026-06-28) and kept only for backward compatibility. The filter is an OR across the
        listed domains: **the candidate pool spans every domain the caller is entitled to, and
        the ranking picks the best across the union.** An empty sequence means no domain filter,
        which is also where ADR-0009's ``domains == []`` clause lives for the predicate
        collection — expressible here, and not expressible with a singular.

        **THE LOOP-AND-MERGE WORKAROUND IS A RANKING CHANGE, NOT AN ERGONOMIC ONE**, which is why
        this is a Protocol-level decision rather than a caller's convenience. One hybrid search
        over three domains returns ONE list scored against one query. Three searches merged
        client-side return three separately-ranked lists whose scores **are not comparable across
        calls**, and the caller has no basis on which to interleave them — the same
        scores-mean-different-things-at-different-doors defect this fleet has already paid for,
        built into the interface instead of stumbled into. It is also N× the embedding cost for
        one phrase.

        **THE RETURN CARRIES ``mode``, AND THAT IS THE WHOLE POINT OF THIS OPERATION'S SHAPE.**
        Both call sites today wrap the embed in ``try/except`` and fall back to BM25, printing to
        stdout — same fields, same score key, no marker. The fleet ran SIXTY-SEVEN DAYS with
        ``LLM_BASE_URL`` unset, every search BM25-only, and nothing in any result said so. A
        degraded retrieval is a MARKED success, never an unmarked one.

        ``mode`` (THE PARAMETER) IS A DIFFERENT AXIS FROM ``MeshResult.mode`` (THE FIELD), AND
        THE SHARED NAME IS A COLLISION, NOT A UNIFICATION — flagged here rather than silently
        left for a caller to conflate. The parameter is a REQUEST: ``"vector_only"`` (the default,
        and today's only behaviour — embedding similarity alone) or ``"hybrid"`` (blend a lexical
        signal, e.g. BM25, into ONE ranked list alongside the vector score). The result field is a
        REPORT of what actually happened, drawn from this interface's own ``MODES`` tuple
        (``"hybrid"`` / ``"bm25"``), and ``"bm25"`` there means an UNPLANNED degradation — the
        embed call failed and the implementation fell back, which is exactly the silent-for-67-days
        failure the field exists to mark. A caller who passes ``mode="hybrid"`` and reads back
        ``result.mode == "bm25"`` has NOT gotten a degraded version of what it asked for in some
        softened sense — it got the embed-failure fallback, same as a ``mode="vector_only"`` caller
        would. Nothing here unifies the two vocabularies; this paragraph exists so a future reader
        does not assume they already are.

        ``metadata_filters`` ADDS A SET-RESTRICTION THE PREDICATE POOL ALREADY NEEDED. A scalar
        value is an exact-match filter (``{"doc_id": "x"}`` → the field equals ``"x"``); a
        ``Sequence`` or ``set`` value is a membership filter (``{"verb_iris": {"a", "b"}}`` → the
        field is IN that set). Both shapes were missing: one call site needs exact-match
        properties and could not express them, and the compat-scoped predicate pool stays
        incumbent today specifically because ``nominate`` has no way to restrict ``verb_iris`` to
        a set. An empty mapping (the default) means no metadata filter, same convention as
        ``domains == ()``. Filters AND together; there is no OR across filter keys — a caller
        needing OR across two metadata values states that as a set-membership filter on one key,
        not as two calls merged client-side, for the same ranking reason ``domains`` is a sequence
        and not a loop.
        """

    def collection_present(self, initiator: Initiator, *, collection: str) -> MeshResult:
        """Is the collection there at all?

        The guard that separates *nothing matched* from *nothing to match against* — two states
        a search alone reports identically, and the reason this is an operation rather than an
        implementation detail.
        """


# ── the write half, ruled 2026-09-27 ────────────────────────────────────────────────────────
#
# SIBLING PROTOCOLS, NOT NEW METHODS ON THE READ INTERFACES ABOVE. Every read Protocol in this
# file stays exactly as pure as its own docstring already claims — `MeshGraph` still has zero
# writes, `MeshOntology`'s `ask`/`construct` still only ask, `MeshVectors.nominate` still only
# searches. A write half bolted onto those as new methods would mean re-reading three docstrings
# that currently say "read-only" and either falsifying them or caveating them into meaninglessness
# — the exact failure this file corrected twice in one day for other reasons. A new class per
# store keeps each read Protocol's own claim true without qualification.


@runtime_checkable
class Embedder(Protocol):
    """What a vectors WRITER is handed, never what it constructs. **Embedding is the writer's job,
    ruled 2026-09-27** — injected so there is exactly ONE place in a running system that probes
    what model an endpoint actually served, rather than a writer holding its own embedding call
    and a reader re-deriving an equivalent probe to compare against. The latter is how
    ``MeshVectors.embedding_model``'s own docstring came to describe the vacuous case this
    contract exists to avoid: two constants agreeing with each other while both disagree with the
    vectors already on disk.

    Two methods, not one, because a normal WRITE and a RELOCATION want different inputs at the
    call site — see :meth:`MeshVectorsWriter.write` and :meth:`MeshVectorsWriter.relocate`. A
    conforming ``Embedder`` is constructed once and held by the writer; nothing in this Protocol
    is ever constructed ad hoc inside a write call, which would reopen the one-probe-one-place
    property this exists to guarantee.
    """

    def embed(self, text: str) -> Sequence[float]:
        """The vector for this text, at whatever model/version this Embedder currently serves."""

    def identity(self) -> tuple[str, Optional[str], int]:
        """``(model, version, dimension)`` — THE SERVED IDENTITY, probed fresh from the endpoint,
        never a constant the caller supplies. The single source both :class:`CollectionMarker`
        and any comparison against it draw from, so a constant-stamping writer and a
        constant-trusting reader cannot agree with each other while both disagree with what an
        endpoint actually served — the same reasoning ``CollectionMarker.model``'s own docstring
        states for the reader side, exercised here on the writer side where the value originates.
        """


class EdgeIdentity(BaseModel):
    """What makes one edge a DIFFERENT edge from another. Four fields, all required, all opaque —
    ``subject``, ``verb`` and ``object`` name the triple; ``key`` is the fourth field, **ruled
    2026-09-29**, and it is what lets two writes of the same triple coexist as two edges rather
    than one write silently overwriting the other.

    ``key`` IS CALLER-SUPPLIED AND THIS SDK NEVER NAMES ONE. The fleet that prompted this field
    passes its own tool-invocation URN (``_tool_urn``); a different caller might pass a batch id,
    a provenance hash, or a session id. This module has no opinion on what a key IS, only that one
    IS the fourth axis of identity — the same "opaque, never parsed" discipline
    :class:`Initiator.subject` states, applied here to what distinguishes an edge rather than who
    is asking for one.

    **IDENTITY IS SEPARATE FROM PAYLOAD, and that is the point of this being its own type rather
    than four more keyword arguments on :meth:`MeshGraphWriter.write_edge`.** Everything in this
    object is what the STORE keys on — two writes whose ``EdgeIdentity`` compares equal are the
    same edge; two whose ``key`` differs are two edges, even with an identical subject, verb and
    object. Whatever a write attaches BEYOND identity (see ``payload`` on ``write_edge``) never
    participates in that comparison.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    verb: str
    object: str
    key: str
    """Caller-supplied. Two edges sharing every other field but this one are still two edges —
    this is the field that makes that true, not an incidental tag alongside identity."""

    @field_validator("subject", "verb", "object", "key")
    @classmethod
    def _field_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(
                f"EdgeIdentity.{info.field_name}='' — every field of identity is required; a "
                f"blank one is not a narrower identity, it is a missing one"
            )
        return v


class EdgeIdentityFilter(BaseModel):
    """What :meth:`MeshGraphWriter.delete_edges` scopes a deletion by — the SAME four fields as
    :class:`EdgeIdentity`, **ruled 2026-09-29** alongside it, each one optional here where none
    were on the write side: an unset field is a wildcard, so a caller can delete one exact edge
    (all four fields bound, matching one ``EdgeIdentity``) or a whole family of them (fewer fields
    bound — every edge for a subject regardless of verb, object or key).

    **REFUSES THE EMPTY FILTER, ON CONSTRUCTION, ALWAYS.** All four fields unset would match every
    edge the store holds — "delete everything" wearing the shape of a scoped call. Three of the
    registrar's four graph paths delete (the reason this method exists at all, ruled alongside
    :meth:`MeshGraphWriter.write_edge`'s amended signature), and none of them means "delete the
    graph"; a filter that could accidentally mean that is refused here rather than trusted to a
    caller who never intended it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: Optional[str] = None
    verb: Optional[str] = None
    object: Optional[str] = None
    key: Optional[str] = None

    @field_validator("subject", "verb", "object", "key")
    @classmethod
    def _bound_field_is_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                f"EdgeIdentityFilter.{info.field_name}='' — omit the field to mean 'any', rather "
                f"than binding it to nothing"
            )
        return v

    @model_validator(mode="after")
    def _at_least_one_field_bound(self) -> "EdgeIdentityFilter":
        if self.subject is None and self.verb is None and self.object is None and self.key is None:
            raise ValueError(
                "EdgeIdentityFilter with every field unset matches every edge in the store — "
                "refused rather than honoured, because 'delete everything' should never be "
                "reachable by omission"
            )
        return self


@runtime_checkable
class MeshGraphWriter(Protocol):
    """Named writes over the property graph. **NO DERIVED INVENTORY EXISTS FOR THIS ONE, and that
    is stated rather than papered over** — the read Protocol's own docstring records "zero Neo4j
    writes" found in the engine-o census that grounded every read operation here; there is no
    equivalent write census this Protocol could derive from, because nothing in the fleet writes
    the property graph today. Declared ahead of a caller anyway, on ruling, matching this file's
    own precedent: `MeshOntology` was declared and later corrected once Jena became a real writer,
    rather than waiting for a caller to justify the shape retroactively.

    **AMENDED IN PLACE, RULED 2026-09-29, ON THE WORKER'S OWN PACKET BACK.** The original ruling
    (2026-09-27) shipped `write_edge(initiator, *, subject, verb, object)` and stated "widening
    this Protocol is a new method with its own manifest and seal." That sentence governs a
    RELEASED contract; nothing tagged has ever carried `MeshGraphWriter` — it has existed only on
    `lane/ca`, uncut — so the correction the worker's packet asked for lands as a signature change
    in place, not a second method beside a wrong first one. Once this Protocol ships in a tagged
    release, the widening-is-a-new-method rule applies again, starting from THIS shape.

    ``write_edge`` now takes **identity separate from payload** — :class:`EdgeIdentity` (subject,
    verb, object, and a caller-supplied ``key``) is what the store keys on; ``payload`` is
    whatever else a write attaches, and never participates in that comparison. The key is what two
    writes of an identical triple need to land as two edges rather than one overwriting the other
    — the defect that sent the worker back with a packet in the first place.

    ``delete_edges`` ships in the SAME ruling, not as a later addition: three of the registrar's
    four graph paths delete, and a writer that cannot express the same identity its own cleanup
    needs would leave the registrar's adoption partial — worse than not adopting the writer at
    all. It is scoped by :class:`EdgeIdentityFilter`, the same four fields, optional, so a caller
    names exactly as much as it means to delete.

    **AMENDED AGAIN, 2026-09-30, ON THE PROMOTION ADAPTER'S OWN REJECTION PACKET BACK**
    (``ia-74/lane/74``, ``IngestGraph``/``IngestIndexes`` in its ``src/iagent/promotion.py``). The
    adapter named three things it lacked; this Protocol gains ``has_edges``, the one of the three
    that is genuinely new here (the other two are satisfied without a new method — see below).
    This still lands IN PLACE rather than as a second ruling, for the same reason the 2026-09-29
    amendment did: nothing tagged has ever carried `MeshGraphWriter`, so the "widening is a new
    method with its own manifest and seal" rule has not started governing it yet — it starts
    the moment v0.9.5 ships this shape.

    ``has_edges`` answers the adapter's "a node-exists read" — reusing :class:`EdgeIdentityFilter`
    rather than inventing a bespoke existence parameter, and :class:`MeshResult` rather than a bare
    ``bool``, the same discipline :meth:`iagent_mesh.interfaces.MeshOntology.ask` already applies:
    ``empty`` means *asked, and nothing matches*, which is a different fact from *could not ask*,
    and collapsing the two into one boolean is exactly the ambiguity this SDK's result types exist
    to refuse.

    The adapter's other two needs are **not** new methods. "A delete-by-block-``ingest_id`` on the
    graph" is already expressible as ``delete_edges(identity_filter=EdgeIdentityFilter(key=
    ingest_id))`` — PROVIDED every fact-triple written for one ingest's provenance shares
    ``EdgeIdentity.key = ingest_id`` as a convention (see
    :attr:`iagent_mesh.provenance.ProvenanceBlock.ingest_id`); ``EdgeIdentity.key``'s own docstring
    already names "a provenance hash" as a legitimate key value, so this is a convention on an
    existing field, not a gap. That a KEY-ONLY filter correctly spans edges differing in subject,
    verb and object was unproven until this same release — see
    ``check_graph_writer_key_only_delete_contract`` in ``iagent_mesh.conformance``, the new arm
    added alongside this amendment. "Any delete on the vectors writer" is answered on
    :class:`MeshVectorsWriter` below, not here.

    **AMENDED AGAIN, 2026-10-01 — OPENS v0.9.6 SCOPE.** v0.9.5 is tagged and this Protocol shipped
    in it, so the "widening is a new method with its own manifest and seal" rule now governs for
    real, for the first time. ``write_node`` lands as exactly that: a NEW method beside the ones
    above, not a signature change to any of them.

    Lane 1 needs it to move the ingest node off ``Neo4jIngestGraph`` — a raw-driver write that
    predates this Protocol existing at all, the same shape of gap ``write_edge`` closed for
    predicate assertions. Everything this Protocol declared until now is EDGE-shaped: subject,
    verb, object. An ingest's own node — the thing whose lifecycle :class:`IngestStatus` tracks
    across ``received`` → ``extracting`` → ``review`` → a terminal stage — is not a
    relationship between two other things, it IS the thing, and nothing here could address it
    without inventing a self-referential triple to stand in for a node that was never an edge.

    ``write_node`` is keyed the same way :meth:`MeshVectorsWriter.write` already keys an object —
    a namespace (``label``, the node's kind) plus a caller-supplied ``id`` unique within it — not
    wrapped in a new identity type the way :class:`EdgeIdentity` wraps four fields, because two
    plain keyword arguments need no validation or optional-filter counterpart a wrapper would
    earn its keep by serving. **No ``delete_node`` or ``has_node`` ships alongside it** — this
    amendment is scoped to exactly what Lane 1 asked for; either could follow on its own packet
    back, the same way ``has_edges`` followed `write_edge`/`delete_edges` rather than shipping
    pre-emptively.

    ``write_node`` IS AN UPSERT, DELIBERATELY UNLIKE ``write_edge``. Two ``write_edge`` calls
    differing only in ``key`` land as two edges — multiplicity is the point, ``key`` is what
    grants it. A node has no such second axis: Lane 1's own use is one ingest, one node, written
    again at every stage transition, and a second write with the SAME ``(label, id)`` must UPDATE
    that node's payload, not mint a second node silently coexisting with the first. A writer that
    treated repeat writes as inserts would leave an ingest with as many phantom nodes as it had
    status transitions — exactly the defect an upsert contract exists to refuse.

    **AMENDED AGAIN, 2026-10-01 — OPENS v0.9.7 SCOPE, ON THE ARCHITECT'S OWN ORDER.** The note just
    above said neither ``delete_node`` nor ``has_node`` ships alongside ``write_node``, and that
    either could follow on its own packet back — this is that packet. Both are genuinely NEW
    methods beside the three ``write_node`` already sits with, not signature changes to any of
    them; v0.9.6 is the release ``write_node`` itself opened scope under, so the same
    widening-is-a-new-method rule already governs this amendment.

    ``has_node`` is ``has_edges`` answered for a node instead of an edge: the same existence-check
    need (idempotency before a write-or-delete decision, not routing), the same reason it lives
    here rather than on the read-only :class:`MeshGraph` (whose reads may be served from a cached
    or derived projection, and would not guarantee read-your-own-write consistency for this
    writer's own prior writes), and the same :class:`MeshResult` return — ``outcome="answered"``
    or ``outcome="empty"``, never a bare ``bool``. It is keyed on plain ``(label, id)``, exactly
    the two arguments ``write_node`` already takes, rather than wrapped in a filter type the way
    ``has_edges`` is scoped by :class:`EdgeIdentityFilter`: a node's identity is already two
    required keyword arguments with no optional/wildcard axis the way an edge's four fields have,
    so there is nothing a filter wrapper would earn its keep by serving here.

    ``delete_node`` mirrors ``delete_edges``'s own idempotency, not its filter shape: deleting a
    ``(label, id)`` that was never written still reports success, the same reasoning
    ``delete_edges``'s own docstring states for a filter matching zero edges — a
    ``DELETE ... WHERE`` with no matching rows still succeeds, and the store now satisfies "this
    node is absent", which may already have been true. It is keyed on ``(label, id)`` for the same
    reason ``has_node`` is: that pair is this Protocol's whole notion of a node's identity, stated
    once by ``write_node`` and reused rather than re-invented by its two siblings.
    """

    def write_edge(
        self,
        initiator: Initiator,
        *,
        identity: EdgeIdentity,
        payload: Mapping[str, str] = MappingProxyType({}),
    ) -> MeshWriteResult:
        """Assert one edge at ``identity``. Person or delegate only — see
        :meth:`Initiator.require_person_or_delegate`.

        Two calls whose ``identity`` differs only in ``key`` land as TWO edges, not one write
        overwriting the other — that is the property ``key`` exists to guarantee, and the
        conformance suite proves it (``one verb, two keys, two edges``) rather than trusting it.
        """

    def delete_edges(
        self, initiator: Initiator, *, identity_filter: EdgeIdentityFilter
    ) -> MeshWriteResult:
        """Remove every edge matching ``identity_filter``. Person or delegate only — see
        :meth:`Initiator.require_person_or_delegate`.

        A filter matching zero edges still reports ``written`` — the store now satisfies "no edge
        matches this filter", which may already have been true; deletion is idempotent by the same
        reasoning a ``DELETE ... WHERE`` with no matching rows still succeeds.
        """

    def has_edges(
        self, initiator: Initiator, *, identity_filter: EdgeIdentityFilter
    ) -> MeshResult:
        """Does any edge matching ``identity_filter`` exist? Person or delegate only — see
        :meth:`Initiator.require_person_or_delegate`.

        **ADDED 2026-09-30**, for a caller (the promotion adapter) that needs to check an edge's
        presence before deciding whether to write or delete it — idempotency, not routing, which
        is why this lives here rather than on the read-only :class:`MeshGraph` (whose reads may be
        served from a cached or derived projection, and would not guarantee read-your-own-write
        consistency for this writer's own prior writes).

        Returns ``MeshResult`` with ``outcome="answered"`` and ``rows`` non-empty when at least one
        edge matches, ``outcome="empty"`` when none do — never a bare ``bool``, so "determined
        absent" stays distinguishable from "could not determine" the same way every other read in
        this SDK keeps that distinction.
        """

    def write_node(
        self,
        initiator: Initiator,
        *,
        label: str,
        id: str,
        payload: Mapping[str, str] = MappingProxyType({}),
    ) -> MeshWriteResult:
        """Upsert one node of kind ``label`` at caller-supplied ``id``. Person or delegate only —
        see :meth:`Initiator.require_person_or_delegate`.

        **ADDED 2026-10-01**, opening v0.9.6 scope, for Lane 1 moving the ingest node off
        ``Neo4jIngestGraph``'s own raw driver write. ``(label, id)`` is this method's whole
        identity — the same "namespace plus caller-supplied id" shape
        :meth:`MeshVectorsWriter.write` already uses, not :class:`EdgeIdentity`'s four fields,
        because a node has no (subject, verb, object) to decompose.

        **UPSERT, not append — the opposite of ``write_edge``'s key-grants-multiplicity rule.** A
        second call with the SAME ``(label, id)`` updates that node's ``payload`` in place; it
        never lands as a second node. This is deliberate: Lane 1's ingest node is written once per
        :class:`iagent_mesh.ingest.IngestStatus` stage transition, and every one of those writes
        must reach the SAME node, the way a row update reaches the same row — if it minted a new
        node per write, "the ingest node" would stop meaning any one thing.
        """

    def has_node(self, initiator: Initiator, *, label: str, id: str) -> MeshResult:
        """Does a node of kind ``label`` at ``id`` exist? Person or delegate only — see
        :meth:`Initiator.require_person_or_delegate`.

        **ADDED 2026-10-01**, opening v0.9.7 scope — the read half ``write_node``'s own docstring
        named as something that could follow on its own packet back. Keyed on plain ``(label,
        id)``, the same two arguments ``write_node`` takes, rather than wrapped in a filter type:
        a node's identity has no optional/wildcard axis the way :class:`EdgeIdentityFilter`'s four
        fields do, so a bespoke filter would earn its keep by serving nothing here.

        Lives on the writer rather than the read-only :class:`MeshGraph`, for the SAME reason
        ``has_edges`` does: a caller needing to check a node's presence before deciding whether to
        write or delete it needs read-your-own-write consistency for THIS writer's own prior
        writes, which a `MeshGraph` read — possibly served from a cached or derived projection —
        would not guarantee.

        Returns ``MeshResult`` with ``outcome="answered"`` and ``rows`` non-empty when the node
        exists, ``outcome="empty"`` when it does not — never a bare ``bool``, the same discipline
        ``has_edges`` already applies, so "determined absent" stays distinguishable from "could
        not determine".
        """

    def delete_node(self, initiator: Initiator, *, label: str, id: str) -> MeshWriteResult:
        """Remove the node of kind ``label`` at ``id``, if one exists. Person or delegate only —
        see :meth:`Initiator.require_person_or_delegate`.

        **ADDED 2026-10-01**, opening v0.9.7 scope, alongside ``has_node`` — the cleanup half
        ``write_node``'s own docstring left open. Keyed on the same ``(label, id)`` pair
        ``write_node`` and ``has_node`` use, this Protocol's one notion of a node's identity.

        Idempotent, the SAME reasoning ``delete_edges`` states for its own filter: a ``(label,
        id)`` matching no node still reports ``written``, because the store now satisfies "this
        node is absent", which may already have been true — deletion is idempotent by the same
        reasoning a ``DELETE ... WHERE`` with no matching rows still succeeds. An implementation
        that reported failure for a never-written ``(label, id)`` would be treating "nothing to
        delete" as an error, which is exactly the defect this contract refuses.

        **STATED, 2026-10-02 (closing the gap ia-74 routed: "is it refused, DETACHed, or
        left?"): a node that still has edges naming it is IMPLEMENTATION-DEFINED, not fixed by
        this Protocol — refuse, detach-and-delete, or delete-and-leave-dangling are all
        conforming, and this is a deliberate non-mandate, not an oversight.**

        ``write_node``/``has_node``/``delete_node`` key on ``(label, id)``; ``write_edge``/
        ``has_edges``/``delete_edges`` key on ``EdgeIdentity``'s ``(subject, verb, object, key)``.
        Nothing in this Protocol couples the two spaces — an edge's ``subject``/``object`` are
        opaque strings, never validated against a node's ``(label, id)`` at write time.

        **Why no universal answer: the three choices are not equally available on every
        backend.** A property-graph store (Neo4j and similar) cannot represent a dangling
        relationship at all — every relationship requires two live endpoint nodes, so deleting a
        node that still has edges either fails outright or must ``DETACH``-delete them with it;
        "leave" is not a storage state that backend can be in. A triple store has no such
        constraint — a dangling reference is an ordinary, representable fact there, and "leave"
        costs that implementation nothing. Mandating "leave" at the Protocol level would make it
        unimplementable on the first backend; mandating "refuse" or "DETACH" would force a
        referential-integrity walk the second backend's model does not otherwise require. Each
        implementation picks the one its own backend actually supports and **documents which**,
        on this method, in its own words — the same "a conscious, discoverable choice, not an
        accident of the backend's native constraints" discipline this Protocol already asks of
        every behavioral fork. Conformance can and should assert the implementation DOCUMENTS its
        choice; it cannot assert WHICH one, because there is no universal right answer to assert
        against.

        For a Neo4j-backed implementation specifically: refuse or ``DETACH DELETE`` are the only
        two storage-level options. A caller who wants delete-then-clean-edges can always do that
        itself with an explicit ``delete_edges`` call first, regardless of which choice this
        method's own implementation makes — that composition works under either.
        """


@runtime_checkable
class MeshVectorsWriter(Protocol):
    """Upsert and relocate within a declared collection. **THE EMBEDDING CONTRACT IS SYMMETRIC
    WITH THE READ SIDE**: :class:`MeshVectors` states "the vector is computed by the caller today"
    as the DEFECT — two implementations handed the same text could embed with two different
    models against one stored index, silently. This Protocol is the fix on the write side: the
    writer holds an injected :class:`Embedder`, embeds internally, and stamps
    :class:`CollectionMarker` from the SAME probe — never a constant, never the caller's job.

    **TWO METHODS BECAUSE TWO CALLERS WANT DIFFERENT THINGS, AND CONFLATING THEM IS THE HAZARD
    RULED AGAINST 2026-09-27.** A normal write hands text; `write` embeds it via this writer's own
    `Embedder` and nothing else may supply a vector for that path. A RELOCATION — moving an
    existing object to a vector computed elsewhere, a re-embed migration, a backfill from a batch
    job — is the only legitimate reason a caller ever holds a precomputed vector, and `relocate`
    is the one and only door for it. A single `write(..., vector=None)`-shaped method that accepts
    either would make "supply your own vector" a normal-looking parameter on the everyday path,
    which is exactly the shortcut this split exists to foreclose.

    **AMENDED 2026-09-30, ON THE PROMOTION ADAPTER'S OWN REJECTION PACKET BACK** (``ia-74/lane/74``
    — see :class:`MeshGraphWriter`'s own 2026-09-30 amendment note for the full context). The
    adapter's third need, "any delete on the vectors writer," had no existing path here at all —
    unlike the graph writer's two needs, this one is genuinely new capability, cleanly additive
    because ``id`` is already first-class identity on this Protocol (unlike the graph writer's
    payload/identity split, nothing here is walled off from being addressed directly).
    """

    def write(
        self,
        initiator: Initiator,
        *,
        collection: str,
        id: str,
        text: str,
        domains: Sequence[str] = (),
        vector_required: bool = True,
    ) -> MeshWriteResult:
        """Upsert one object by a caller-supplied deterministic id, embedding ``text`` via this
        writer's injected :class:`Embedder`.

        ``vector_required`` DEFAULTS ``True``. When the embed fails and the caller has not passed
        ``vector_required=False``, the write is REFUSED — never silently completed without a
        vector, which is the sixty-seven-day silent-BM25 defect replayed at write time. Passing
        ``vector_required=False`` is the caller saying, at this call, that a vectorless write is
        acceptable; the writer must never decide that on its own.
        """

    def relocate(
        self, initiator: Initiator, *, collection: str, id: str, vector: Sequence[float]
    ) -> MeshWriteResult:
        """Move an existing object to a PRECOMPUTED vector. RELOCATION ONLY.

        Never a shortcut for `write` — this method does not embed, does not accept ``text``, and
        an implementation must refuse a vector whose length does not match this writer's declared
        dimension rather than storing a vector no query at this dimension could ever retrieve.
        """

    def delete(self, initiator: Initiator, *, collection: str, id: str) -> MeshWriteResult:
        """Remove one object by its caller-supplied ``id`` within ``collection``. Person or
        delegate only — see :meth:`Initiator.require_person_or_delegate`.

        **ADDED 2026-09-30**, symmetric with `write`/`relocate`: ``id`` is the same first-class
        identity those two already address by. Idempotent, the same reasoning
        :meth:`MeshGraphWriter.delete_edges` states for its own filter — an ``id`` that matches
        nothing still reports ``written``, because the store now satisfies "this id is absent",
        which may already have been true.
        """


@runtime_checkable
class MeshOntologyWriter(Protocol):
    """Named writes over the RDF store, GRAPH-scoped by construction. Ruled 2026-09-27 to close
    the defect :class:`MeshOntology`'s own docstring now names: three of doc-tools' four
    SPARQL-emitting plugins insert into Jena's *default* graph, invisible to the mesh resolver,
    because nothing at the write call forces scoping. See
    ``iagent_mesh.writers.jena.JenaOntologyWriter`` for the reference implementation this SDK
    ships.

    ``graph`` is REQUIRED on `upsert`, never optional. The read side's `graph` is optional because
    a read can legitimately mean "anywhere within scope"; a write choosing "anywhere" is precisely
    the unscoped default-graph insert this Protocol exists to make impossible to express, so the
    asymmetry with the read Protocol's optional `graph` is deliberate, not an inconsistency.
    """

    def upsert(
        self, initiator: Initiator, *, graph: str, iri: str, triples: Sequence[str]
    ) -> MeshWriteResult:
        """Replace every triple this writer previously wrote for ``iri`` within ``graph`` with
        ``triples`` — delete-then-insert, both halves GRAPH-scoped to the same graph, in one
        update so there is no window where the graph holds neither the old state nor the new one.

        Person or delegate only. An implementation must refuse (never silently default) an empty
        ``graph`` — see :meth:`Initiator.require_person_or_delegate` for the identity boundary and
        the reference implementation for the refusal shape on an unscoped request.
        """
