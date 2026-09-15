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
        """The model this implementation embeds with. Asserted against the collection's."""

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
