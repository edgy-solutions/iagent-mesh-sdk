# Substrate Interfaces: `iagent_mesh.interfaces`

**Status:** shipped in SDK `0.9.3`. **Both import paths work** — the root one is
new in `0.9.3`, and the sentence here previously said it would fail.

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
| `kind` | `"person"` \| `"service"` | **Declared, never sniffed.** |

The model is frozen and forbids extra fields. An empty or whitespace `subject` is
refused at construction: *an anonymous read is not a read with a missing name, it
is a read nobody can be held to.*

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
from iagent_mesh.interfaces import ServiceIdentityRefused

try:
    graph.registry(service_initiator)
except ServiceIdentityRefused as exc:
    ...  # names the operation and the subject
```

`ServiceIdentityRefused` subclasses `PermissionError` and is deliberately *not* a
generic authz error: it names the one condition, so reading the raise teaches you
the rule rather than telling you something was denied. A read attributed to a
service records provenance no person can be asked about.

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

> **There is no write half, and for a specific reason: there is no verified
> working path.** The update endpoint is derived by replacing `/sparql` with
> `/update` in an endpoint spelled `.../ds/query` — no configured endpoint
> contains `/sparql`, so the substitution is a no-op and the "write" posts
> `update=` to the *query* endpoint. Promising a write half over an untested route
> would make the breakage look like an implementation bug rather than an absence.

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

## 8. Quick reference

```python
from iagent_mesh.interfaces import (
    Initiator, ServiceIdentityRefused,
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
    assert_fixture_discriminates, ConformanceFailure,
)
```

Deprecated, removed after in-fleet callers move: `marker_is_stale`.
