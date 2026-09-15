"""The mesh has one client: named operations that carry the caller and record what they read.

An engine sees the substrate through these Protocols and never through a query language or a
connection string. This is ADR-0049's bypass rule generalised from *"do not read the graph
directly"* to **"do not hold a driver at all"** — and it is ``run_any_graph`` for stores: a
Cypher or SPARQL slot is arbitrary code in a query's clothes.

── THE SDK OWNS INTERFACES AND IMPORTS NO IMPLEMENTATION AND NO DRIVER ─────────────────────
Nothing here imports ``neo4j``, ``weaviate-client``, ``rdflib`` or ``httpx``. A Protocol that
imported its implementation would make the dependency real however the module is named — R-038's
rule, and there is a seal asserting it rather than a comment claiming it.

**Enforcement of the ban is NOT here and is not a name list.** It is a NetworkPolicy: a pod that
cannot route to the store cannot reach it whatever it imports. Three findings drove that and each
defeats a name-based instrument on its own — *the import name is not the capability* (``rdflib``
parses local Turtle and is not a driver), *the pyproject is not the import*
(``agent_fleet/utils/`` has no pyproject and three engines import it), and *the import is not the
connection* (Jena is reached by raw ``httpx``; Weaviate by ``urllib.request``, which ships with
Python and can never be banned).

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

from typing import Literal, Optional, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator

from .results import MeshResult

__all__ = [
    "Initiator",
    "ServiceIdentityRefused",
    "MeshGraph",
    "MeshOntology",
    "MeshVectors",
    "MESH_COLLECTION_META",
    "CollectionMarker",
    "CorruptCollectionMarker",
    "collection_marker",
    "read_collection_marker",
    "marker_is_stale",
]


class ServiceIdentityRefused(PermissionError):
    """A service identity reached an operation that requires an initiator.

    Not a generic authz error on purpose: this names the ONE condition, so a caller reading the
    raise learns the rule rather than that something was denied.
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
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    """The authorization identity, opaque. Whatever claim the deployment keys on."""

    kind: Literal["person", "service"]

    @field_validator("subject")
    @classmethod
    def _subject_is_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "initiator subject is empty — an anonymous read is not a read with a missing "
                "name, it is a read nobody can be held to"
            )
        return v

    def require_person(self, operation: str) -> "Initiator":
        """Refuse a service identity, naming the operation. The boundary check, in one call.

        Implementations call this FIRST in every operation. It is a method rather than a note in
        the Protocol docstring because a rule an implementer has to remember is a rule that holds
        until someone is busy.
        """
        if self.kind == "service":
            raise ServiceIdentityRefused(
                f"{operation} requires an initiator and received a service identity "
                f"({self.subject!r}). A read attributed to a service records provenance no "
                f"person can be asked about."
            )
        return self


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
        """Predicates that can operate on ``subject``, walking the ancestor chain."""

    def ancestors(self, initiator: Initiator, iri: str, *, max_hops: int) -> MeshResult:
        """The ``subClassOf`` chain.

        REFUSES RATHER THAN DEGRADING: a failed ancestor walk silently narrows verb
        compatibility and returns classification to pre-ADR-0018 behaviour, and a degraded answer
        there is indistinguishable from a considered one.
        """


@runtime_checkable
class MeshOntology(Protocol):
    """Named reads over the RDF store. **NO WRITE HALF, and for a different reason than MeshGraph.**

    MeshGraph has no write half because there is no caller. This one has none because **there is
    no verified working path**: the update endpoint is derived by ``endpoint.replace("/sparql",
    "/update")`` from an endpoint spelled ``.../ds/query`` — no configured endpoint contains
    ``/sparql``, so the substitution is a NO-OP and the write posts ``update=`` to the QUERY
    endpoint. It does not derive the wrong address; it derives nothing while reading exactly like
    a derivation.

    **Promising a write half over an untested route is worse than omitting one**, because the
    interface would make the breakage look like an implementation bug rather than an absence.
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


def marker_is_stale(marker: CollectionMarker, oldest_object_unix_ms: Optional[int]) -> bool:
    """Does this marker predate the collection it claims to describe?

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
        """

    def collection_present(self, initiator: Initiator, *, collection: str) -> MeshResult:
        """Is the collection there at all?

        The guard that separates *nothing matched* from *nothing to match against* — two states
        a search alone reports identically, and the reason this is an operation rather than an
        implementation detail.
        """
