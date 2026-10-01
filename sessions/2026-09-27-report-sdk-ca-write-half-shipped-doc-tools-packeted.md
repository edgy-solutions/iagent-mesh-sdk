# Report — the v0.9.5 write half: implemented, tested, documented, committed; doc-tools packeted

to: the architect (via Chris)
from: iagent-mesh-sdk / `lane/ca`, 2026-09-27
re: the five-item ruling on the write half, following the v0.9.4 cut

---

## Status: all five ruling items shipped on `lane/ca`. Not released. Not merged.

**No release of v0.9.5 without Chris's explicit word** — nothing below changes that; it's restated
because item 5 below required contacting doc-tools, and that contact could be misread as "ready to
ship." It isn't, until told otherwise.

Three commits, in order:

1. `5205d04` feat(interfaces): the write half — sibling Protocols, `MeshWriteResult`, wider write
   boundary. `iagent_mesh/write_results.py`, `iagent_mesh/interfaces.py`,
   `iagent_mesh/conformance.py`, `iagent_mesh/__init__.py`, plus
   `tests/test_writer_interfaces.py` and `tests/test_write_results.py`. 7 files, +823/−9.
2. `9882aca` feat(writers): `JenaOntologyWriter` — the `MeshOntologyWriter` reference
   implementation. `iagent_mesh/writers/jena.py` (+`__init__.py`), plus `tests/test_jena_writer.py`
   and `tests/test_writer_conformance.py`. 4 files, +510.
3. `2edc13d` docs(interfaces): document the write half (§4a) and correct the stale v0.9.4 note.
   `README.md`, `docs/interfaces.md`. 2 files, +175/−14.

Full suite after all three: **552 passed, 2 skipped, 0 failed.** No regressions.

## Ruling items, against what shipped

1. **Sibling Protocols; reads stay pure.** `MeshGraphWriter` / `MeshVectorsWriter` /
   `MeshOntologyWriter`, all new classes in `interfaces.py`. `MeshGraph` / `MeshOntology` /
   `MeshVectors` gained zero methods — pinned by exact `dir()`-set assertion in
   `test_writer_interfaces.py::test_the_read_interfaces_gained_NO_new_method`, checked against the
   live runtime before being trusted.
2. **Embedder injected once; relocate takes a precomputed vector as a separate method.**
   `Embedder` Protocol (`embed`, `identity`) is constructor-injected into a vectors writer, never
   built per-call. `MeshVectorsWriter.write` embeds via the injected `Embedder`;
   `MeshVectorsWriter.relocate` takes `vector` directly and has no `text` parameter — asserted by
   signature inspection, not just by reading the source.
3. **Outcomes, `vector_required` default.** `MeshWriteResult` — `written | written_without_vector
   | refused | failed | unreachable`, `detail` required on every outcome but `written`, `.applied`
   true only for the two written-* outcomes, `bool()` raises `AmbiguousWriteResultTruth`,
   `.require()` raises `WriteNotApplied`. `MeshVectorsWriter.write`'s `vector_required` defaults
   `True` (signature-asserted); `written_without_vector` is reachable only by explicit opt-out.
4. **`require_person_or_delegate`; never bare service.** Admits `person` and `delegate`, refuses
   `service` via the existing `ServiceIdentityRefused` — no new exception class, since a delegate
   never reaches a branch that would raise `DelegateIdentityRefused` at this boundary (asserted
   directly: calling it on a delegate must never raise that exception). A service is refused the
   *same way* at both the read and write boundaries — the write boundary is wider by one kind, not
   a differently-shaped gate.
5. **`JenaOntologyWriter` ships as the reference implementation; packet doc-tools.**
   `iagent_mesh/writers/jena.py` — one `POST update=` per upsert to `/{dataset}/update`, both the
   `DELETE WHERE` and `INSERT DATA` halves `GRAPH`-wrapped in the *same* request (no two-round-trip
   window), `graph`/`iri` validated against `<`, `>`, whitespace before interpolation, empty
   graph/iri/triples and bare-service all refuse before any I/O, 5xx and connection errors map to
   `unreachable` rather than `failed`. Conformance arm: `check_ontology_writer_contract` proves
   scoping took effect by *asking* — not by trusting the reported outcome — with a
   fixture-discrimination check ahead of the two specific failure messages, so a fixture that
   can't tell scoped from unscoped writes refuses on that basis before either message is reachable.
   Packeted to doc-tools today (below) now that it's on a branch, per this item.

## Test coverage added, and what each arm is proven to catch

- `tests/test_writer_interfaces.py` (17 tests) — the wider write boundary (5 tests), the read
  interfaces' unchanged shape (1), the three writer Protocols' ruled shape (6), and
  `check_writer_offline` biting on: an accepted service identity, a refused delegate, a bare-bool
  return, and an empty operations list (4 break-on-purpose tests plus 1 positive control).
- `tests/test_jena_writer.py` (16 tests) — against `httpx.MockTransport`, asserting the *decoded*
  request body (not just the outcome) GRAPH-wraps both halves; exactly one request per upsert;
  service refused with zero I/O; delegate admitted; five parametrized malformed/empty-input
  refusals, each with zero I/O; `httpx.RequestError` and 502/503/504 both map to `unreachable`
  (not `failed`); a genuine 400 maps to `failed` and carries the status in `detail`; structural
  `isinstance` check against `MeshOntologyWriter`.
- `tests/test_writer_conformance.py` (9 tests) — `check_ontology_writer_contract` against an
  in-memory scoped store (positive control) and four broken variants: lands only in the "default"
  graph while reporting `written` (the literal doc-tools defect this arm exists to catch), an
  upsert that never applies, a leak into the default graph despite correct within-graph placement,
  and a store that persists nothing at all (caught by the fixture-discrimination check, not the
  two specific messages) — plus two fixtures that can't discriminate at all (always-answers,
  always-empty), both refused on that basis. `check_writer_offline`'s remaining
  `NotImplementedError` arm and its two-operation positive control round it out.

Two things worth naming rather than leaving implicit: the body-content assertion in
`test_jena_writer.py` had to decode the form-urlencoded wire body before checking for the `GRAPH`
clauses — an outcome-only check would have passed a writer that silently dropped the GRAPH clause
and landed the triple in Jena's default graph, which is the exact defect this class exists to make
unrepresentable. And in `test_writer_conformance.py`, `check_ontology_writer_contract`'s
fixture-discrimination check runs *before* its two outcome-specific checks, so most naively-broken
fixtures hit the generic "does not discriminate" message first; the four broken variants above were
built to genuinely differ between within-graph and default-graph outcomes so the specific messages
stay reachable and tested.

## Docs

`docs/interfaces.md` gained §4a ("The write half") — boundary, `MeshWriteResult`, `Embedder`, the
three Protocols in a table, `JenaOntologyWriter` usage, and both conformance checks, each with a
one-line statement of what it proves. Two stale claims fixed in the same commit: the `MeshOntology`
blockquote still described the pre-ruling "no write half, nobody's ruled GRAPH scoping" state
(the ruling closed that 2026-09-27); §8's status line still said v0.9.4 "has not been cut" (it has,
and is published — `c75587e`/tag/PyPI, verified last segment). `README.md` gained one bullet
pointing at §4a and restating the release gate.

## Sent today: packet to doc-tools

Filed as an uncommitted file in `doc-tools/sessions/` (never committed by the sending lane, per the
lane-packet convention) —
`2026-09-27-packet-to-7f-writer-shipped-vocab-graph-not-mine.md`. Covers: the write half's shape as
above; how `JenaOntologyWriter` relates to doc-tools' own PR #23 scoping fix in `execute_update`
(same posture — refuse rather than silently default-graph — reached structurally differently: the
SDK writer never receives an opaque body to inspect, it only ever emits scoped ones); and a ruling
on the vocabulary-graph-refusal gap doc-tools-52 flagged (*"the writer does NOT currently refuse a
body scoped to the vocabulary graph... if your write half can close it, say so and I'll stop
treating it as mine"*) — **ruled not the SDK's to close**: `MeshOntologyWriter.upsert` takes `graph`
as an opaque required string with no concept of "vocabulary" vs `_INSTANCES", and per this SDK's
generic-at-birth constraint it will not acquire domain-naming knowledge to tell them apart; the
distinction is `plugin.domain_label`-keyed policy that has to live at the call site building the
`graph=` argument — i.e., in the replace-PR that swaps `semantic_assets.py:531` for this writer,
the same way PR #23 already keys its own wrap on `plugin.domain_label`. Suggested (not built by me)
a belt-and-suspenders assertion at that call site rather than in the SDK.

Acknowledged doc-tools' standing instruction relayed from the architect — 7f replaces
`semantic_assets.py:531` with this writer and deletes the old path in the same PR, first caller of
the write half — nothing further needed from `lane/ca` until that PR is up.

## Open, for the record

- No response yet from doc-tools on today's packet (just sent).
- No memory update filed yet for this arc's closure — will follow once doc-tools' replace-PR gives
  a first real caller to confirm the shape against, rather than writing it down twice.
- **v0.9.5 remains uncut and unreleased. Waiting on Chris's word, as instructed, before any tag or
  publish.**

Lane: ia-ca/lane/ca
