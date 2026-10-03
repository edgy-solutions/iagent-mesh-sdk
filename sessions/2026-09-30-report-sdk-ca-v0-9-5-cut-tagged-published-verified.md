# Report — v0.9.5 cut, tagged, published, verified

to: Chris
from: iagent-mesh-sdk / `lane/ca`, 2026-09-30

Order (pasted content, `to: iagent-mesh-sdk/lane/ca`): "CUT v0.9.5 now: cut → pin → declare,"
plus three preconditions before cutting — evaluate the worker's three needed calls, add
`ingest_id` to `ProvenanceBlock`, mark the Jena writer experimental — and a four-recipient report
after. Your own word, carried from earlier, was the gate: "my word is go on v0.9.5."

## Before cutting

1. **The worker's (`ia-74/lane/74`) three needed calls**, evaluated against `MeshGraphWriter`/
   `MeshVectorsWriter` and judged against each one's own "once tagged, widening needs a new
   ruling" bar. All three were additive — none deferred to 0.9.6, so the order's fallback (stub +
   defer) was never invoked:
   - **`MeshGraphWriter.has_edges(initiator, *, identity_filter)`** — new method, same
     `answered`/`empty` discipline `MeshOntology.ask` already uses for existence checks.
   - **Delete-by-`ingest_id` on the graph** — no new method. The existing
     `delete_edges(identity_filter=EdgeIdentityFilter(key=ingest_id))` already does this, *provided*
     the worker stamps `EdgeIdentity.key = ProvenanceBlock.ingest_id` on every fact-triple for one
     ingest. The one gap: nothing had proven a key-only filter (subject/verb/object all wildcarded)
     reaches edges differing in all three, not just within one `(subject, verb)` pair. New
     conformance arm `check_graph_writer_key_only_delete_contract` proves it now.
   - **`MeshVectorsWriter.delete(initiator, *, collection, id)`** — new method, cleanly additive
     since `id` is already first-class identity on this writer (symmetric with `write`/`relocate`).
   - New conformance arm `check_vectors_writer_delete_contract` for the vectors delete, using
     structural introspection (`contains_after_delete`) rather than a read-side round trip, since
     `nominate` is fuzzy/ranked and can't serve as a presence oracle (the same limitation its own
     `check_vectors_writer_contract` already states).
   - All three arms built with the house discipline: positive control + every named defect.
2. **`ProvenanceBlock.ingest_id: str | None`** added — same optionality discipline as
   `derived_from`, present on the wire only when set. This is the field the worker's cleanup reads
   to populate the `key=` filter above.
3. **Jena writer marked EXPERIMENTAL** — `JenaOntologyWriter`'s docstring now states it has no
   caller in this fleet yet and that the first caller lands in 0.9.6.
4. Reachability test caught the three new conformance names not re-exported from
   `iagent_mesh/__init__.py` — fixed, full suite reran clean (642 passed, 2 skipped).

Commit: `0eca2a3` on `lane/ca`, "feat(writers): the promotion adapter's three needed calls, plus
ingest_id and the Jena experimental mark" — 8 files, 513 insertions, 7 deletions.

## The cut

Same procedure as v0.9.4, repeated exactly:

1. **Branch check both directions**, suite run before merge (642 passed, 2 skipped).
2. **Merged `lane/ca` → `master`, `--no-ff`**, no squash — clean, no conflicts (23 files, 4683
   insertions, 29 deletions).
3. **PyPI checked live before tagging** (direct API hit, not cached): `GET
   /pypi/iagent-mesh/0.9.5/json` → 404. 0.9.5 did not exist.
4. **Bumped `pyproject.toml` to 0.9.5, `uv lock` regenerated**, suite rerun green, tree clean.
   Committed (`ceab07a`, "chore(release): bump version to 0.9.5"). Tagged and pushed `v0.9.5`.
5. **CI, all three jobs green**: Test (14s) → Build wheel (16s) → Publish to PyPI via OIDC trusted
   publishing (20s). Run `36800276263`. No manual upload.
6. **Verified from the consumer side**, fresh `uv venv` in `/c/tmp/verify_iagent_mesh_095` (outside
   any git tree): `iagent_mesh.__file__` resolved into that venv's `site-packages`, not this
   checkout; dist-info `Version: 0.9.5`; downloaded the actual wheel from
   `files.pythonhosted.org`, sha256 `898b013a239e624b242446adfed8e25992d9ba9ce7a0fb43e0b36aa2d1d903d8`
   matched PyPI's declared digest exactly; `has_edges`, `delete`, `ingest_id` all present on the
   installed package; all 5 scaffold templates present in the wheel.
7. `lane/ca` fast-forwarded to `ceab07a` and pushed.

**Tag:** `v0.9.5`, pushed, pointing at `ceab07a` on `master`. **PyPI:** live,
`iagent-mesh==0.9.5`, wheel + sdist, digest-verified.

## Reported out

Packet filed: `invincible-agent/sessions/2026-09-30-packet-from-ca-v0-9-5-cut-tagged-published-verified.md`,
addressed to Lane 1 (`ia-01/lane/01`), the worker (`ia-74/lane/74`), cortex
(`ia-cortex-60/lane/cortex-60`), and 7f (`doc-tools/lane/7f`). Covers the tag/PyPI result, release
notes (provenance block, ingest wire shapes, writer Protocols, Jena experimental), and — for the
worker specifically — the resolved design for all three needed calls plus the `key=ingest_id`
convention it depends on.

## Carried forward

- Jena writer's first caller is a 0.9.6 commitment, not yet assigned.
- The worker should build directly against `has_edges`/`delete_edges(key=...)`/`delete` now that
  they're live — no stub needed.
- No open design questions from this order remain; all five sub-tasks closed.

Lane: ia-ca/lane/ca
