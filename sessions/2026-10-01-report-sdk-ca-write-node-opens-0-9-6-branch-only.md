# Report — write_node lands on `MeshGraphWriter`, opens v0.9.6, branch only

to: Chris
from: iagent-mesh-sdk / `lane/ca`, 2026-10-01

Order (pasted content, `to: iagent-mesh-sdk/lane/ca`): "0.9.6 scope opens with write_node on
MeshGraphWriter (Lane 1 needs it to move the ingest node off Neo4jIngestGraph). Branch only; no
tag."

## What shipped, on `lane/ca` only

`MeshGraphWriter.write_node(initiator, *, label: str, id: str, payload)` — a NEW method, not a
signature change to `write_edge`/`delete_edges`/`has_edges`. This is the first widening since
`MeshGraphWriter` shipped tagged in v0.9.5, so its own 2026-09-29 rule ("widening is a new method
with its own manifest and seal") governs for real for the first time, and this change honors it.

**Keyed like `MeshVectorsWriter.write`**, not like `EdgeIdentity`: a namespace (`label`) plus a
caller-supplied `id`, two plain keyword arguments rather than a new wrapper type — there's no
delete/filter counterpart yet to justify one. No `delete_node`/`has_node` shipped alongside it;
out of scope for this order, can follow on their own packet if Lane 1 needs them.

**Upsert semantics, the deliberate opposite of `write_edge`'s key-grants-multiplicity rule.** A
node has no second identity axis the way an edge's `key` gives it one — Lane 1's own use is one
ingest, one node, rewritten at every `IngestStatus` stage transition. A second `write_node` call
at the same `(label, id)` updates that node, it does not mint a second one.

## Conformance

New arm `check_graph_writer_write_node_contract`: since no node-read Protocol method exists
(there's deliberately no `has_node`), it verifies structurally via the implementer's own
introspection — the same pattern `check_vectors_writer_delete_contract` used for its
`contains_after_delete`. Catches both "stores nothing" and "silently keeps the first write" as
the same discriminate-failure class. Positive control + 3 named-defect tests.
`MeshGraphWriter`'s method-set pin test updated; re-exported from `iagent_mesh/__init__.py` so
the reachability test doesn't repeat the gap the v0.9.5 cut caught.

Full suite: 647 passed, 2 skipped (642 at the v0.9.5 tag + 5 new).

## Status

Commit `c5fec43` on `lane/ca`, pushed. **No tag, no PyPI publish, no merge to `master`** — per
the order, branch only. Lane 1 can build against this by pinning a git dependency on `lane/ca` at
this commit; it is not installable from PyPI until 0.9.6 is actually cut.

Not reported to Lane 1, the worker, cortex, or 7f — this order named no recipients (unlike the
v0.9.5 order's explicit four), so nothing was sent. Say the word if you want Lane 1 told it's
ready to build against.

Lane: ia-ca/lane/ca
