# Substrate Interfaces: `iagent_mesh.interfaces`

**Status:** shipped in SDK `0.9.3`. **Both import paths work** — the root one is
new in `0.9.3`, and the sentence here previously said it would fail.

**The write half** ([§4a](#4a-the-write-half)) is ruled and shipped on `lane/ca`,
pending `v0.9.5` — no release without explicit sign-off.

```python
from iagent_mesh import Initiator, MeshGraph, MeshOntology, MeshVectors, MeshResult
```

The module paths keep working and nothing needs to change:

```python
from iagent_mesh.interfaces import Initiator, MeshGraph, MeshOntology, MeshVectors
from iagent_mesh.results import MeshResult
```

Prefer the root. Importing by module path makes the FILE part of the contract, so a
definition cannot move without every consumer seeing a rename — which is the reason
the names were promoted.

> ⚠ **Not everything is at the root, and the omissions are deliberate rather than
> incomplete.** `task_kinds` and `discovery` each export `resolve`, and `task_kinds`
> also collides with `graph_manifest` on `compose`, `json_schema` and `validate_dir`.
> A root carrying both sides of a collision would answer one caller's question with
> the other's function, so those modules are imported by path until the names are
> settled. `tests/test_every_public_name_is_reachable.py` records which modules are
> exported, which are declined, and why.

**What `0.9.3` also carries:** the `[server]` extra (`pip install 'iagent-mesh[server]'`
for the engine host and the auth dependency — the client surface needs neither), the
`mesh:enumerateInstances` request/response shape with `scoped_by`, the edge-type
registries, and the `SOURCE_LEDGER` row vocabulary.

---

## 1. What this is, in one paragraph

An engine sees the substrate through three `Protocol`s — `MeshGraph` (property
graph), `MeshOntology` (RDF store), `MeshVectors` (vector store) — and never
through a query language or a connection string. There is no `run_cypher`, no
`run_sparql`, no driver handle. The operations are **named reads**: each one
carries *who is asking* as its first argument, and each one returns the same
result type that can say *whether the substrate answered at all*.

Two rules fall out of that and are worth reading before the API:

- **A query-language slot is arbitrary code in a query's clothes.** The reason
  there is no `run_any_graph(cypher)` escape hatch is not ergonomics — it is that
  such a slot cannot be authorized, cannot be attributed, and cannot be reasoned
  about. If an operation you need is missing, the fix is a new named operation on
  the Protocol, not a passthrough.
- **The SDK owns the interfaces and imports no implementation and no driver.**
  Nothing in `interfaces.py` imports `neo4j`, `weaviate-client`, `rdflib` or
  `httpx`, so you can depend on this module from anywhere without pulling a
  substrate client into your environment.

There are two audiences below. [§2–§5](#2-who-is-asking-initiator) are for
**consumers** — engine authors calling these. [§6](#6-implementing-an-interface)
is for **implementers** — adapter authors satisfying them.

---

## 2. Who is asking: `Initiator`

Every operation takes an `Initiator` as its first positional argument. Identity is
an **argument, not ambient state**, because reads are visibility-filtered per
caller and are recorded as provenance under that caller.

```python
from iagent_mesh.interfaces import Initiator

who = Initiator(subject="alice@example.com", kind="person")
```

| Field | Type | Meaning |
| --- | --- | --- |
| `subject` | `str` | The authorization identity, **opaque**. Whatever claim your deployment keys on — an email, an employee id, a Keycloak name. The SDK never parses it. |
| `kind` | `"person"` \| `"service"` \| `"delegate"` | **Declared, never sniffed.** |
| `on_behalf_of` | `str \| None` | Who a **delegate** is accountable to. Required (non-blank) when `kind == "delegate"`, refused otherwise. **Provenance, never a gate input** — no guard reads it. |

The model is frozen and forbids extra fields. An empty or whitespace `subject` is
refused at construction: *an anonymous read is not a read with a missing name, it
is a read nobody can be held to.*

`"delegate"` (added 2026-09-27) is a non-human session acting under its **own**
entitlements — a lane worktree, a scheduled job — distinct from a `"service"`
(a deployed workload with no one to ask about it) and from a `"person"` (whose
grants it must not silently inherit). `on_behalf_of` names who it acts for, for
the audit trail; it is kept separate from `subject`, the field a gate checks, on
purpose — the two questions happen to share a value today and must stay free to
diverge.

### Why `kind` is declared rather than inferred

The obvious implementation of "refuse service identities" is to look for a `svc:`
prefix or a `service-account-` shape in the subject. That is exactly what this SDK
will not do: subject spellings differ per deployment, so a parser that works in
your sandbox **mislabels silently** at work — both readings produce a plausible
identity. The classification comes from the token's claims at the edge that minted
it and travels here as a declared field.

> This is not in tension with the policy validator refusing a `svc:` prefix in a
> disclosure grant. There the spelling is *ours* — a declaration on the git rail
> that we write and review. Here the subject arrives from someone else's issuer,
> and constraining its format asserts a fact about a system we do not own.
> Same-looking rule, opposite direction of authority.

### Service identities are refused at the boundary

```python
from iagent_mesh.interfaces import ServiceIdentityRefused, DelegateIdentityRefused

try:
    graph.registry(service_initiator)
except ServiceIdentityRefused as exc:
    ...  # names the operation and the subject
except DelegateIdentityRefused as exc:
    ...  # a delegate is refused too, but as a SIBLING condition, not this one
```

`ServiceIdentityRefused` and `DelegateIdentityRefused` both subclass
`PermissionError` and are deliberately *not* one generic authz error: each names
the one condition it means, so reading the raise teaches you the rule rather than
telling you something was denied. `ServiceIdentityRefused` — a read attributed to
a service records provenance no person can be asked about. `DelegateIdentityRefused`
— a delegate acts under its own grants, and this operation is not one of them.

`require_person` is an **allowlist** (`kind == "person"` is admitted; every other
kind is refused), not a check for `"service"` specifically — a comparison the other
way round would silently admit any kind declared after it was written, which is
exactly how `"delegate"` would have slipped through the old body.

Implementations enforce this by calling `initiator.require_person(operation)` as
their first line — see [§6](#6-implementing-an-interface).

---

## 3. What comes back: `MeshResult`

Every read on every interface returns one type. **It has four outcomes, and
collapsing them is the defect this type exists to end.**

```python
OUTCOMES = ("answered", "empty", "failed", "unreachable")
```

| Outcome | Meaning | Class |
| --- | --- | --- |
| `answered` | Asked; rows came back. | success |
| `empty` | Asked; **nothing matched**. A real answer. | success |
| `failed` | Asked; the substrate refused or errored. | failure — a query defect |
| `unreachable` | **Could not ask.** | failure — a deployment defect |

`failed` and `unreachable` are separate because the operator's remedy differs.
`answered` and `empty` are both successes because the substrate replied.

### Fields

| Field | Notes |
| --- | --- |
| `outcome` | one of the four above |
| `rows` | `tuple[T, ...]` — non-empty iff `answered`; empty otherwise (enforced) |
| `mode` | *How* it was answered, where a mode exists (`"hybrid"`/`"bm25"` for vectors); `None` where the interface declares none |
| `detail` | Why, for a failure. **Required** on `failed` and `unreachable` |

The model validates state coherence at construction, so these are
unrepresentable:

- `answered` with no rows — *that is `empty`*
- a non-`answered` result carrying rows — *the silent-fallback shape*
- `failed`/`unreachable` with no `detail` — *a failure that cannot say why*

`mode` must arrive already normalised (lowercase, stripped). A non-normalised
spelling is **refused rather than corrected**: silently rewriting `"BM25"` into
`"bm25"` would be a silent correction inside a type built to end silent
corrections, and the typo is the implementer's to find.

### Reading one

```python
r = graph.verbs_for(who, subject="mesh:Document", max_hops=3)

if r.outcome == "unreachable":
    ...                      # deployment problem — page someone
elif r.answered_ok:          # True for BOTH answered and empty
    for row in r.rows:
        ...
else:
    log.error("read failed: %s", r.detail)
```

Or, when a failure should propagate:

```python
rows = r.require("verbs_for")   # () on `empty`; raises ResultNotAnswered on a FAILURE
```

### `if result:` raises — on purpose

```python
if r:            # ← AmbiguousResultTruth
    ...
```

`__bool__` refuses, because a truth value would have to collapse `empty`, `failed`
and `unreachable` into one branch. Use `r.outcome`, `r.answered_ok`, or
`r.require()`. `answered_ok` is a named property rather than `bool()` so a reader
can see *which* question is being asked.

### Constructors (implementer-facing, but they document the states)

```python
MeshResult.answered(rows, mode=None)
MeshResult.empty(mode=None)
MeshResult.failed(detail, mode=None)
MeshResult.unreachable(detail)
```

### Caching note

`unreachable` **must never be cached.** One blip would silence enumeration for a
whole TTL — which is how a failed provider lookup came to render as "no provider
is registered". `answered` and `empty` are checked answers and are cacheable;
`unreachable` is the absence of an answer.

---

## 4. The three interfaces

All three are `@runtime_checkable` Protocols, and each declares a `MODES` tuple.
`MODES` is declared **even when empty**, so a consumer can tell "no mode exists
here" from "the implementation forgot".

### `MeshGraph` — named reads over the property graph

`MODES = ()` — one way to answer, so its results carry no mode.

**Read-only, and that is ruled rather than an omission.** There are no
property-graph writes to model here: the writer is the registrar, and state writes
go through the mesh writer with `DERIVED_FROM`. A write half added "for symmetry"
would mint a surface whose only caller does not exist.

| Operation | Returns |
| --- | --- |
| `registry(initiator)` | Which personas and domains are active |
| `providers_for(initiator, verb)` | Engines registered as providers of `verb` |
| `classes_with_a_verb(initiator, domains, *, include_referents=False)` | Classes carrying a verb in these domains — the productive-option gate |
| `data_assets_for(initiator, iri)` | Physical dataset URNs behind an ontology IRI |
| `edge(initiator, subject, verb)` | One predicate edge, cheapest by cost class |
| `path(initiator, start, end, *, cost_classes)` | Shortest composition within the allowed cost classes |
| `operable_subjects(initiator, domain)` | Classes with at least one registered verb, domain-scoped and **visibility-filtered for this initiator** |
| `verbs_for(initiator, subject, *, max_hops)` | Predicates that can operate on `subject`, walking the ancestor chain |
| `ancestors(initiator, iri, *, max_hops)` | The `subClassOf` chain |

Two dispositions worth knowing as a caller:

- **`classes_with_a_verb` degrades open at the *call site*, not in the
  operation.** Its caller treats an empty as *do not filter*, because failing
  closed empties the candidate pool and takes routing down globally. That
  disposition belongs to the caller and is written there; the operation still
  reports `failed` honestly. If you call it, you choose your own disposition — and
  you should write it down at the call site.
- **`ancestors` refuses rather than degrading.** A failed ancestor walk silently
  narrows verb compatibility, and a degraded answer there is indistinguishable
  from a considered one.

### `MeshOntology` — named reads over the RDF store

`MODES = ()`.

| Operation | Returns |
| --- | --- |
| `ask(initiator, *, iri, graph=None)` | Does this IRI (optionally within this graph) resolve? |
| `construct(initiator, *, subject, graph=None)` | A typed subgraph as Turtle, **term types intact** |

`ask` is a boolean question that still returns `MeshResult`: `empty` means *asked,
and it does not exist*, which is not *could not ask*. Collapsing those is how a
write came to be guarded by a check that could not fail.

`construct` exists rather than a SELECT because the SELECT executor drops term
types — a typed read has to be a CONSTRUCT and a parse, not a SELECT and a guess.

**What an implementation is held to** ([§6](#ontology-implementations-one-extra-check)):

- `ask` on an IRI that does not exist answers `empty` — never `failed`,
  `unreachable`, or a raised exception, and never `answered`. A caller that gets
  `failed` from a legitimate absence cannot tell *no* from *could not ask*.
- `ask` on an IRI that does exist answers `answered`. Without this, an `ask` that
  is always `empty` would satisfy the rule above.
- `construct` answers with Turtle **text** (`str` rows) that still carries its term
  types: `"42"^^xsd:integer` stays typed, `"hello"@en` keeps its tag.

> **Status: the contract has a conformance arm and no implementation.** No
> `MeshOntology` implementation exists in the fleet yet, and the entry-point group
> `iagent_mesh.ontology` is unfilled. `check_ontology_contract` is proven against
> in-memory fakes, not against a real RDF store.

> **The write half now exists — this note is the second correction the same day
> forced.** The route works (`POST update=<sparql>` to `{fusekiUrl}/ds/update`
> returns 200, measured by `doc-tools/lane/7f` against sandbox Fuseki, and no live
> code derives that address by an `endpoint.replace("/sparql", "/update")`
> substitution — removed 2026-09-14 as a latent hazard). What was genuinely
> missing was a ruling on who owns SPARQL `GRAPH` scoping for a write, closed
> 2026-09-27: see [§4a](#4a-the-write-half) below. `MeshOntology` itself is
> **unchanged and stays pure** — the write half is a sibling class, never a new
> method here.

### `MeshVectors` — semantic lookup within a declared collection and domain

`MODES = ("hybrid", "bm25")`.

| Member | Notes |
| --- | --- |
| `embedding_model` (property) | The model this implementation embeds with — part of the contract, asserted **at open** |
| `nominate(initiator, *, collection, text, domains=(), limit=10)` | Candidate rows for a phrase |
| `collection_present(initiator, *, collection)` | Is the collection there at all? |

**`collection_present` is an operation, not an implementation detail**, because a
search alone reports *nothing matched* and *nothing to match against*
identically.

#### `domains` is a sequence, and that is load-bearing

The filter is an OR across the listed domains: the candidate pool spans every
domain the caller is entitled to, and the ranking picks the best **across the
union**. An empty sequence means no domain filter.

Do **not** loop over domains and merge client-side. That is a *ranking* change,
not an ergonomic one: one hybrid search over three domains returns one list scored
against one query, while three searches merged client-side return three
separately-ranked lists whose scores **are not comparable across calls** — and you
have no basis on which to interleave them. It is also N× the embedding cost for
one phrase.

#### Always read `mode` on a nominate result

```python
r = vectors.nominate(who, collection="OntologyClass", text=phrase, domains=["legal", "ops"])
if r.mode == "bm25":
    log.warning("retrieval degraded to BM25 — embeddings unavailable")
```

This fleet ran **sixty-seven days** with `LLM_BASE_URL` unset, every search
BM25-only, and nothing in any result said so. A degraded retrieval is a *marked*
success, never an unmarked one — which is why `mode` is on the result type and why
`MODES` is declared per interface.

#### Why `embedding_model` is on the interface at all

The vector is computed by the **caller** — the vector store here is dumb storage
with no vectorizer module on the cluster side. So a bare `nominate(text)` would be
a lie by omission: two implementations handed the same text can embed with two
different models against one stored index, and nothing in the call would say so.

Checked **at open, not per query**: open is the one moment both sides pass
through, and a per-query check costs a round trip on every search *while still
leaving the first write unguarded* — and a write with the wrong model is as much
the failure as a read. Three states:

```
matching      → open
mismatching   → refuse, naming BOTH
absent        → open, and REPORT THE GAP ONCE
```

**Absent must never be silently treated as matching.** Readers land before
writers, so metadata is missing for a while — swallowing that arrives dressed as
tolerance and is exactly the vacuous self-comparison the property exists to
avoid.

---

## 4a. The write half

**Status: shipped, unreleased.** Ruled 2026-09-27 on
`invincible-agent/sessions/2026-09-27-proposal-from-ca-a-write-half-for-meshgraph-and-meshvectors.md`,
ships in the SDK's `lane/ca` branch pending `v0.9.5`. **No release of `v0.9.5`
without explicit sign-off** — do not treat this section's presence as a release.

The read Protocols above stay exactly as pure as their own docstrings claim.
Writes are **sibling Protocols**, never new methods bolted onto `MeshGraph`,
`MeshOntology` or `MeshVectors` — a write half added as new methods there would
mean re-reading three "read-only" docstrings and either falsifying or caveating
them, the same failure this file corrected twice in one section above.

```python
from iagent_mesh import (
    Embedder, MeshGraphWriter, MeshVectorsWriter, MeshOntologyWriter,
    EdgeIdentity, EdgeIdentityFilter,
    MeshWriteResult, WriteOutcome, WRITE_OUTCOMES,
    AmbiguousWriteResultTruth, WriteNotApplied,
)
```

### The write boundary is wider than the read boundary

Every read refuses everything but a person: `initiator.require_person(op)`. A
write admits a **person or a delegate**, refusing only a bare service:

```python
initiator.require_person_or_delegate("ontology.upsert")
```

A delegate — a lane worktree, a scheduled job, acting under its own entitlements
— is exactly who this boundary exists to admit, and no new exception exists for
it: a delegate never reaches a branch that would raise `DelegateIdentityRefused`
here, only `ServiceIdentityRefused`, the same exception the read side raises for
the same identity.

### `MeshWriteResult` — the write-side sibling of `MeshResult`

```python
WRITE_OUTCOMES = ("written", "written_without_vector", "refused", "failed", "unreachable")
```

| Outcome | Meaning |
| --- | --- |
| `written` | Landed, clean. |
| `written_without_vector` | Landed, **without** a vector — see below. Not a success dressed down; a distinct state. |
| `refused` | Declined before touching the store (a bad input, an identity gate). |
| `failed` | The store was asked and errored. |
| `unreachable` | Could not be asked. |

`written_without_vector` sits apart from `written` in every idiom that would
otherwise fold them together — the same discipline `MeshResult` applies to
`answered`/`empty`, extended here because a degraded landing wearing a plain "it
worked" is the sixty-seven-day silent-BM25 defect replayed at write time.
`detail` is required on every outcome except `written`, `written_without_vector`
included.

```python
result.applied     # True for BOTH written and written_without_vector
result.require("vectors.write")   # raises WriteNotApplied, naming outcome + detail
bool(result)        # raises AmbiguousWriteResultTruth — always use .outcome or .applied
```

### `Embedder` — injected, never constructed ad hoc

```python
class Embedder(Protocol):
    def embed(self, text: str) -> Sequence[float]: ...
    def identity(self) -> tuple[str, Optional[str], int]: ...   # (model, version, dimension)
```

A vectors writer is **handed** an `Embedder`, never builds one inside a write
call — one identity probe, one place, so the model/version/dimension a
`CollectionMarker` stamps is the same probe that produced the vector, not a
constant a reader re-derives to compare against.

### The three writer Protocols

| Protocol | Operation(s) | Notes |
| --- | --- | --- |
| `MeshGraphWriter` | `write_edge(initiator, *, identity, payload={})`; `delete_edges(initiator, *, identity_filter)` | **Amended in place, ruled 2026-09-29**, on the worker's own packet back — see below. |
| `MeshVectorsWriter` | `write(initiator, *, collection, id, text, domains=(), vector_required=True)`; `relocate(initiator, *, collection, id, vector)` | **Two methods on purpose.** `write` embeds `text` via the injected `Embedder`; `relocate` takes a precomputed vector for migration/backfill only. One method accepting either would make "supply your own vector" a normal-looking parameter on the everyday path. |
| `MeshOntologyWriter` | `upsert(initiator, *, graph, iri, triples)` | `graph` is **required**, never optional — the read side's optional `graph` can mean "anywhere within scope"; a write choosing "anywhere" is the unscoped-default-graph defect this Protocol exists to make unrepresentable. |

#### `MeshGraphWriter` — identity separate from payload, ruled 2026-09-29

The original declaration (`write_edge(initiator, *, subject, verb, object)`) was
minimal on purpose but flattened two different things into one argument list:
what edge this is, and what it carries. The worker's own packet back on the
first conformance arm found the seam. Amended, **in place** — not as a new
method — because nothing tagged has ever carried `MeshGraphWriter`; it exists
only on the uncut `lane/ca`. The "widening is a new method with its own
manifest and seal" rule in this Protocol's docstring applies to *released*
contracts; once `v0.9.5` is tagged, this shape is what it applies to.

```python
class EdgeIdentity(BaseModel):        # frozen, extra="forbid"
    subject: str
    verb: str
    object: str
    key: str   # caller-supplied; the SDK never names one — e.g. this fleet passes `_tool_urn`

class EdgeIdentityFilter(BaseModel):  # frozen, extra="forbid"
    subject: Optional[str] = None
    verb: Optional[str] = None
    object: Optional[str] = None
    key: Optional[str] = None
    # refuses construction if ALL FOUR are None — an unscoped filter would delete every edge

def write_edge(initiator, *, identity: EdgeIdentity, payload: Mapping[str, str] = {}) -> MeshWriteResult: ...
def delete_edges(initiator, *, identity_filter: EdgeIdentityFilter) -> MeshWriteResult: ...
```

The caller-supplied `key` is what makes two writes of the same
`(subject, verb, object)` under two different keys land as **two edges**, not
one overwriting the other — the conformance arm below exists specifically to
catch a writer that collapses `key` out of identity. `delete_edges` was ruled
part of the write half, not a later addition: three of the registrar's four
graph paths delete, and the writer and the cleanup must agree on identity or a
partial adoption of this contract is worse than none — hence `identity_filter`
sharing `EdgeIdentity`'s four fields, each optional, to scope a deletion as
narrowly or as broadly as the caller can name.

**Conformance arm — one verb, two keys, two edges** (`check_graph_writer_contract`,
extended 2026-09-29): writes the same `(subject, verb, object)` twice under two
different keys, then reads back edges for that `(subject, verb)` and requires
**exactly two rows**. A writer that keys storage on `(subject, verb)` alone,
ignoring `key`, returns one row here and the arm fails by name — this is the
defect the worker's packet named, made unable to pass silently.

**Conformance arm — delete by identity** (`check_graph_writer_contract`,
extended 2026-09-29 overnight, closing the gap disclosed the same day): reuses
the two-key state above rather than standing up a third write. Deletes by an
`EdgeIdentityFilter` scoped to the FIRST key only, then reads back and requires
**exactly one row** — the second key's edge, untouched. Two wrong counts are
two different defects, named separately: **zero rows** means the delete
over-matched and removed the second key's edge too, the writer and the cleanup
no longer agreeing on identity; **two rows** means the delete reported
`written` and removed nothing — the same write-side lie this suite refuses to
trust from a reported outcome alone, now caught on the delete path. No gap
remains disclosed here: `delete_edges` now has its own "verify the mutation
applied" arm, the same discipline `write_edge` has above it.

`MeshVectorsWriter.write`'s `vector_required` **defaults `True`**: an embed
failure refuses the write rather than silently landing without a vector.
Passing `vector_required=False` is the caller opting into a degraded write at
*this* call; the writer must never decide that on its own.

### `JenaOntologyWriter` — the reference implementation

```python
from iagent_mesh.writers.jena import JenaOntologyWriter

writer = JenaOntologyWriter(base_url="http://fuseki:3030", dataset="ds")
result = writer.upsert(who, graph="http://mesh/g", iri="http://mesh/thing",
                        triples=["<http://mesh/thing> a <http://mesh/Class> ."])
```

Not importable from `iagent_mesh` root or from `iagent_mesh.interfaces` — it
lives in `iagent_mesh.writers`, a separate subpackage, so `interfaces.py`'s own
"imports no driver" claim (naming `httpx` specifically) stays literally true.
`httpx` is already a hard SDK dependency; the boundary this split draws is
*which module may import it*, never whether it may be installed.

Closes the exact defect `doc-tools/lane/7f` measured: three of doc-tools' four
SPARQL-emitting plugins insert into Jena's **default** graph, invisible to the
mesh resolver, because nothing at the write call forced scoping.
`upsert()` has no path that skips the `GRAPH` clause — one request, `DELETE
WHERE`/`INSERT DATA` **both** wrapped in `GRAPH <graph> { ... }`, so there is no
window where the graph holds neither the old state nor the new one. `graph` and
`iri` are validated against `<`, `>` and whitespace before being interpolated
into a SPARQL IRI reference; `triples` are trusted as already-formed statements,
the same boundary `MeshOntology.construct` places on a caller reading Turtle
back. A `502`/`503`/`504` reports `unreachable` (a proxy/deployment problem);
any other non-`200` reports `failed`; an `httpx.RequestError` reports
`unreachable`.

### Conformance: two new arms

```python
from iagent_mesh.conformance import check_writer_offline, check_ontology_writer_contract

check_writer_offline(
    impl,
    operations=[("upsert", lambda who: impl.upsert(who, graph=G, iri=IRI, triples=T))],
)
```

`check_writer_offline` is `check_offline`'s write-side sibling, drawn **wider on
purpose**: it asserts a service is refused and **both** a person and a delegate
are admitted, each call returning `MeshWriteResult`. Reusing `check_offline`
here would fail every conforming writer, since the read arm's narrower
person-only gate refuses the exact delegate identity a writer must admit.

```python
check_ontology_writer_contract(
    call_upsert=lambda: writer.upsert(who, graph=G, iri=IRI, triples=T),
    call_ask_within_graph=lambda: reader.ask(who, iri=IRI, graph=G),
    call_ask_default_graph=lambda: reader.ask(who, iri=IRI, graph=None),
)
```

This arm proves scoping **took effect** rather than trusting the upsert's own
reported outcome: it asks the same IRI back, once scoped to the graph just
written and once against Jena's default graph, and fails unless the scoped ask
answers while the default-graph ask stays empty. A writer that reported
`written` while landing unscoped cannot pass by reporting alone — the lie does
not survive being asked.

---

## 5. The collection marker

A **marker collection** (`MESH_COLLECTION_META == "MeshCollectionMeta"`) is what a
writer records about a vector collection and what a reader checks at open. It is a
carrier that is ours by construction — the alternative, encoding into the store's
human `description` field, offers three choices and all three are traps: overwrite
loses a sentence with nothing red, refuse turns the check into the thing that gets
muted, and splice is *a parser over a field that was never a format*.

### `CollectionMarker`

| Field | Notes |
| --- | --- |
| `collection` | The collection described |
| `model` | **The SERVED identity** — what the embeddings endpoint *said it used*, not what you asked for and not a constant |
| `version` | `Optional[str]`. **Absent is a state, not a value.** If filled it must be an immutable identity — a digest, never a tag |
| `dimension` | **The observed vector length**, never a constant |
| `written_by` | Which *side* stamped it — the repo or service, not the asset |
| `collection_created_unix_ms` | The collection's creation stamp as the writer observed it |

Frozen, extra fields forbidden, and every string field must be non-empty: *a
marker that cannot discriminate is not a marker*.

**`model` is the served identity for a measured reason.** A constant records what
the code *believes*. `LLM_EMBED_MODEL` overrides the default at runtime on both
sides — so a writer that stamps its constant and a reader that compares its
constant **agree with each other while both disagree with the vectors on disk**.
An OpenAI-compatible embeddings response carries `model` in the same payload as
the vector it describes; reading it is free, provider-neutral, and catches the
case neither constant reaches.

> ⚠ Expect this consequence: a collection written while the endpoint was
> misconfigured records the wrong model **faithfully**. That marker will disagree
> with both constants and will look like a bug — and it will be the only thing in
> the system telling the truth about what produced those vectors.

**`version` is `Optional` rather than a sentinel** because a sentinel is still a
string and `marker.version == mine.version` matches it happily. A comparison runs
only when *both* sides carry one; otherwise the version is reported
**unverified**, never silently agreed. A digest cannot be a contract requirement —
the routes exposing one are provider-specific while the fleet configures an
OpenAI-compatible base URL — so an Ollama-backed writer *may* enrich this field
and a LiteLLM-backed writer honestly reports absence. This is stated, not enforced
in code: rejecting "a tag" would mean parsing a provider-specific string format,
which is the same mistake as sniffing an identity's shape.

### Writing and reading one

```python
from iagent_mesh.interfaces import (
    collection_marker, read_collection_marker, CorruptCollectionMarker,
)

# WRITER — in the SAME ACT that creates the collection
raw = collection_marker(
    collection="OntologyClass",
    model=response.model,                         # the SERVED identity
    dimension=len(response.data[0].embedding),    # the OBSERVED length
    written_by="doc-tools-sync",
    collection_created_unix_ms=now_ms,
    version=None,                                 # or an immutable digest
)

# READER
try:
    marker = read_collection_marker(raw)   # None means ABSENT — never "matches"
except CorruptCollectionMarker:
    ...   # OUR record damaged. NOT the same as absent: nobody-wrote-one is a gap,
          # something-wrote-ours-badly is a failure, and they want opposite behaviours.
```

Write the marker as a **fold, not a hand-run step**. A marker written by a
separate step is a marker that can be forgotten, and a forgotten marker reads as
*absent* while the collection is perfectly real.

> ⚠ **Writer-side requirement, declared rather than discovered:** on re-ingest the
> objects' creation times **must move forward**. The staleness check below has no
> collection-level timestamp and proxies it with the oldest object's. A writer
> that preserves original object timestamps through a re-ingest silently defeats
> the check — it keeps passing and means nothing.

### What a marker check establishes — as data, not prose

```python
from iagent_mesh.interfaces import MARKER_ASSERTS, MARKER_DOES_NOT_ASSERT

MARKER_ASSERTS           # ("model", "dimension")
MARKER_DOES_NOT_ASSERT   # ("currency",)
```

A passing `check_embedding_contract` means the collection's vectors were written
by the declared model and dimension — **two witnesses** — and says **nothing**
about whether they are current. Freshness is **out of scope in the contract**,
declared here rather than implied by a green or corrected in a docstring. A
property that cannot be established must be named as unasserted, or its absence
reads as its presence.

### `marker_predates_collection` — and its live caveat

```python
marker_predates_collection(marker, oldest_object_unix_ms) -> bool
```

Named for what it *can* assert. It computes
*absent-or-older-than-the-oldest-object*, which is not the same claim as "stale".

> ⚠⚠ **This proxy is already defeated in the current fleet — measured, not
> predicted — and must not be relied on until it is replaced.** The writer
> rewrites objects in place on deterministic UUIDs and the store *preserves*
> `creationTimeUnix` across a replace. Measured 2026-09-15: 132 of 132 sampled
> `Predicate` objects carry an update time later than their creation time, widest
> gap 81 days. The oldest object's creation time does not move while the vectors
> underneath are rewritten. **Treat a non-stale verdict from this function as
> UNPROVEN, never as evidence of freshness.**

It ships in this state deliberately and *declared*: a known-broken check that says
so is a gap with an owner; the same check shipped silent is the confident green
the mechanism exists to end. The replacement under ruling makes staleness
*unrepresentable* rather than detectable — refresh the marker in the same act that
writes vectors, not only at creation.

Note also: **an empty collection cannot be dated**, and that returns `True`
(treated as absent) rather than valid — treating an undatable marker as current is
the confident-stale reading the field exists to prevent.

### Deprecated: `marker_is_stale`

`marker_is_stale()` is the old name and delegates to
`marker_predates_collection()`, emitting a `DeprecationWarning`. It is kept for
one dual-key interval because the name is public in `0.9.0`/`0.9.1` — a rename
needs an expand/contract interval, not a clean cut.

**The in-fleet caller has now moved** (engine-o's `mesh_vectors._ensure_opened`, and
its own seal asserts it does not drift back). An audit across every repo checked out
locally finds no remaining importer — only prose mentions in a ruling doc and a
comment. **That audit covers the repos on one machine, not the world:** the name was
the *real* function in `0.9.0`/`0.9.1`, so anyone installing from PyPI on those
versions has a caller nobody here can see, and they get one release of deprecation
warning rather than an interval. **It is removed in a later release, deliberately —
not in `0.9.3`.** Migrate now:

```diff
- from iagent_mesh.interfaces import marker_is_stale
- if marker_is_stale(marker, oldest):
+ from iagent_mesh.interfaces import marker_predates_collection
+ if marker_predates_collection(marker, oldest):
```

---

## 6. Implementing an interface

**An implementation is admitted by passing the conformance suite, never by being
named in the SDK.** Run it in your own CI, pinned to the SDK minor, so the
contract cannot drift silently under you — the suite moves with the SDK and your
build goes red.

### The shape of an implementation

```python
from iagent_mesh.interfaces import Initiator, MeshGraph
from iagent_mesh.results import MeshResult


class Neo4jMeshGraph:                 # no explicit inheritance — it is a Protocol
    MODES: tuple[str, ...] = ()

    def registry(self, initiator: Initiator) -> MeshResult:
        initiator.require_person("registry")     # FIRST LINE. Always.
        try:
            rows = self._driver_call(...)
        except ConnectionError as exc:
            return MeshResult.unreachable(f"graph store unreachable: {exc}")
        except Exception as exc:
            return MeshResult.failed(f"registry query failed: {exc}")
        return MeshResult.answered(rows) if rows else MeshResult.empty()
```

`require_person` is a **method on `Initiator` rather than a note in the Protocol
docstring**, because a rule an implementer has to remember is a rule that holds
until someone is busy. Call it first in every operation.

Four obligations, all of which conformance checks:

1. Every operation takes the initiator and **refuses a service identity**.
2. Every operation returns a `MeshResult` — never a bare list.
3. An operation that emits a `mode` emits only a value its interface **declared**.
4. An operation on a declared interface **answers or refuses, never
   `NotImplementedError`**.

### The offline arm — always run this

```python
from iagent_mesh.conformance import check_offline

check_offline(
    impl,
    operations=[
        ("registry",      lambda who: impl.registry(who)),
        ("providers_for", lambda who: impl.providers_for(who, verb="mesh:startReview")),
        ("ancestors",     lambda who: impl.ancestors(who, iri="mesh:Document", max_hops=3)),
        # ... every operation you implement
    ],
    declared_modes=impl.MODES,
)
```

You supply the `(name, call)` pairs because only you know what arguments your
operations need. **A suite over an empty list passes everything** — `check_offline`
refuses an empty `operations`, because that is the likeliest way to satisfy
conformance without conforming.

### The live arm — needs a real substrate

```python
from iagent_mesh.conformance import check_live

check_live(
    impl,
    operation="registry",
    call_reachable_empty=lambda: impl_pointed_at_empty_store.registry(person),
    call_unreachable=lambda: impl_pointed_at_dead_host.registry(person),
    read_provenance=lambda: fetch_provenance_subjects(),   # optional
)
```

This arm exists because **provenance-recorded cannot be faked**: asserting that an
implementation *would* record what it read asserts nothing. An offline-only suite
admits an implementation that records nothing.

`call_reachable_empty` must hit a substrate that **is** reachable and holds
nothing; `call_unreachable` must hit one that cannot be reached. **The two must not
be the same fixture wearing two names** — that is checked, not assumed. A
conformance run that only ever feeds an empty store passes an implementation that
swallows every error.

### The fixture rule

```python
from iagent_mesh.conformance import assert_fixture_discriminates
```

**A fixture is a legal input that happens to make two behaviours identical.** An
alphabetical-order fixture cannot tell *sorted* from *preserved*; an empty-store
fixture cannot tell *answered nothing* from *failed silently*. The suite asserts
its own fixtures discriminate **before** the arm that uses them, rather than
carrying a list of remembered instances — both of its authors shipped an
undiscriminating fixture. Use this helper in your own arms too.

### Ontology implementations: one extra check

```python
from iagent_mesh.conformance import check_ontology_contract, check_offline

person = Initiator(subject="user:someone", kind="person")

check_ontology_contract(
    impl,
    call_ask_present=lambda: impl.ask(person, iri=EXISTING_IRI),
    call_ask_absent=lambda: impl.ask(person, iri=IRI_THAT_EXISTS_NOWHERE),
    call_construct=lambda: impl.construct(person, subject=EXISTING_IRI),
    typed_terms=['"42"^^xsd:integer', '"hello"@en'],   # as YOUR serializer emits them
)
```

You supply the fixture; the SDK ships no RDF dependency. The subject behind
`EXISTING_IRI` must carry **at least one datatype literal and one language-tagged
literal**, and `typed_terms` are the exact substrings your serializer writes for
them. The check is a substring match, so it is a floor: parse the Turtle in your
own test if you want term types compared structurally.

The arm refuses a fixture that cannot discriminate (present and absent must answer
differently; a term with no datatype and no tag cannot tell *typed* from *stripped*),
and refuses `typed_terms=()`. It does **not** assert what `construct` returns for
an absent subject — the Protocol does not say. Run `check_offline` as well, for the
service-identity refusal and the `MeshResult` return type.

### Vector implementations: two extra checks

```python
from iagent_mesh.conformance import check_embedding_contract, check_writer_marker

check_embedding_contract(
    operation="nominate",
    declared_model=impl.embedding_model,
    expected_dimension=768,
    read_stored_dimension=lambda: probe_stored_vector_length(),
    declared_version="",                       # optional
    read_marker=lambda: fetch_marker_raw(),
    read_oldest_object_unix_ms=lambda: oldest_creation_ms(),
    report_gap=lambda msg: log.warning(msg),   # for the ABSENT state
)

# WRITERS are admitted by round-tripping through the contract's own reader
check_writer_marker(
    collection="OntologyClass", model="nomic-embed-text", dimension=768,
    written_by="doc-tools-sync", collection_created_unix_ms=now_ms,
)
```

`read_stored_dimension` returning `None` is a **failure**, not "the collection is
empty": it is the one check available today failing to run, and a skipped check
reads exactly like a passed one.

`check_writer_marker` exists so **neither side writes a parser** — there is one
implementation of the write and an admission check over its output, so writer and
reader cannot drift. That property survived two changes of carrier unchanged,
because it is what made each of them safe.

All failures raise `ConformanceFailure` (an `AssertionError`), and it always names
the operation.

---

## 7. Adding an operation

If you need something the Protocols do not offer, **add a named operation** — do
not add a query passthrough and do not reach around the interface. A new operation
must:

- take `initiator` as its first argument and refuse a service identity;
- return `MeshResult`, with the four states meaning what they mean here;
- declare any `mode` it can emit in its interface's `MODES`;
- be derived from a real caller. The existing operations are a census of what
  direct substrate accesses were *trying to do*, not a table of what an interface
  ought to offer. An operation whose only caller does not exist is the same
  mistake as a query slot, applied to shape instead of arbitrariness.

---

## 8. Saying how a figure was computed: `MethodBlock`

```python
from iagent_mesh.models import MethodBlock, MethodInput, ToolOutput

class RateOutput(ToolOutput):
    total: float

out = RateOutput(
    total=100.0,
    method=MethodBlock(
        formula="rate * hours",
        inputs=[
            MethodInput(name="rate", value=12.5, unit="USD/h"),
            MethodInput(name="hours", value=8),
        ],
        bound=40.0,
        bound_defaulted=True,          # the producer filled the bound in; the caller did not
        producer_sha="3f2a91c",        # the code that computed it
    ),
)
```

This is not a substrate interface; it lives here because it answers the same question
the result types do — *what should a reader believe about this value* — for a number
instead of a read.

`ToolOutput.method` is **optional and additive**. An output that sets none dumps
exactly what it dumped before, with no `method: null` key, and a subclass that
already declares its own field named `method` keeps it.

| Field | Meaning |
| --- | --- |
| `formula` | How the figure was produced. Required, not blank. |
| `inputs` | `MethodInput(name, value, unit=None)` for each input, with the value it took. The value keeps its type (`12` stays an `int`, `True` a `bool`). `unit=None` means *no unit stated*, not *dimensionless*. |
| `bound` | An optional numeric bound the computation ran under. |
| `bound_defaulted` | `True` if the producer supplied the bound, `False` if the caller did, `None` if the producer did not say. **`None` is not `False`**: an unmade claim is not a claim the caller chose the bound. |
| `producer_sha` | The code that produced the figure. Required, not blank. |

**`bound` and `bound_defaulted` must agree on whether there is a bound** — enforced
at construction (added 2026-09-27, reconciling this model with a fleet producer
that was already checking it): `bound is None` and `bound_defaulted is None` are
the same state or the block is refused. A bound with no word on where it came from,
or a flag on a measure that states no bound, is the half-stated disclosure the pair
exists to end.

`MethodBlock` is `extra="forbid"` and frozen: a misspelt key is refused rather than
dropped. It records what the producer **says** about its method; nothing in the SDK
verifies that the formula is the one that ran or that `producer_sha` is the sha that
was deployed.

> **Shipped in v0.9.4**, cut and published 2026-09-27.

---

## 9. Quick reference

```python
from iagent_mesh.interfaces import (
    Initiator, ServiceIdentityRefused, DelegateIdentityRefused,
    MeshGraph, MeshOntology, MeshVectors,
    MESH_COLLECTION_META, CollectionMarker, CorruptCollectionMarker,
    collection_marker, read_collection_marker, marker_predates_collection,
    MARKER_ASSERTS, MARKER_DOES_NOT_ASSERT,
)
from iagent_mesh.results import (
    MeshResult, Outcome, OUTCOMES, AmbiguousResultTruth, ResultNotAnswered,
)
from iagent_mesh.conformance import (
    check_offline, check_live, check_embedding_contract, check_writer_marker,
    check_ontology_contract, assert_fixture_discriminates, ConformanceFailure,
    check_writer_offline, check_ontology_writer_contract,
)
from iagent_mesh.models import MethodBlock, MethodInput, ToolOutput

# the write half — see §4a. Status: shipped, unreleased (pending v0.9.5).
from iagent_mesh import (
    Embedder, MeshGraphWriter, MeshVectorsWriter, MeshOntologyWriter,
    MeshWriteResult, WriteOutcome, WRITE_OUTCOMES,
    AmbiguousWriteResultTruth, WriteNotApplied,
)
from iagent_mesh.writers.jena import JenaOntologyWriter
```

Deprecated, removed after in-fleet callers move: `marker_is_stale`.
