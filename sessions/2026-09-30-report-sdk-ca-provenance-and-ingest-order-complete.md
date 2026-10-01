# Report — provenance block + ingest wire shapes order, all three items closed

sdk-ca, 2026-09-30

## Order

```
to: iagent-mesh-sdk/lane/ca
1. Provenance block model in iagent_mesh with the OBTAINED_VIA enum including user-drop, and a builder
   doc-tools can import (doc-tools depends on iagent-mesh, not iagent; 7f measured the stamp is
   unreachable from there). This unblocks 7f's ingress-user sensor. First.
2. IngestRequest, IngestStatus (stage enum), ContentKind derived from registrations, and the
   kind-registration row model (kind, passes, outputs). Packet Lane 1, cortex and 7f with wire shapes.
3. Conformance arms as usual. No tag; v0.9.5 still Chris's word.
```

## What shipped

Commit `b68926a` on `lane/ca` — `iagent_mesh/provenance.py` (item 1),
`iagent_mesh/ingest.py` (item 2), `tests/test_provenance.py` (15 tests) and
`tests/test_ingest.py` (31 tests) (item 3), plus the root re-exports in
`iagent_mesh/__init__.py` and the `_EXEMPT` entries in
`tests/test_every_public_name_is_reachable.py` for the two new
`compose`/`validate_dir` collisions `ingest.py` inherits from reusing
`declarations.py`'s composer.

Full suite: 630 passed, 2 skipped, 0 failed.

## Item 2's packet

Filed to all three named recipients in one file, since no prior packet in
`invincible-agent/sessions/` addressed more than two and a comma-joined
`to:` line has precedent there:

    invincible-agent/sessions/2026-09-30-packet-from-ca-provenance-block-and-ingest-wire-shapes.md
    to: ia-01/lane/01, ia-cortex-60/lane/cortex-60, doc-tools/lane/7f

Covers both wire shapes, the `ProvenanceIncomplete`-vs-`ValidationError`
exception-shape split (with an explicit "gate on this one, not that one"
instruction), and a flagged warning that `resolve_content_kind` HALTS
(`ContentKindUnregistered`) rather than degrading — contrasted by name
against `task_kinds.resolve`'s TOTAL pattern, since a lane copying that
pattern here would reintroduce the silent-default hole ADR-0021 exists to
close.

## Design notes worth carrying forward

- `ProvenanceIncomplete` is raised directly by the builder/gate functions,
  never inside a pydantic `field_validator` — pydantic-core re-wraps a raised
  `ValueError` subclass into a generic `ValidationError` there, which would
  silently make `ProvenanceIncomplete` uncatchable by name on that path.
  `ProvenanceBlock`'s own validators raise plain `ValueError` instead, and a
  dedicated test proves the two entry points actually diverge rather than
  documenting that they should.
- `resolve_content_kind` is deliberately NOT total, unlike
  `task_kinds.resolve` — ADR-0021 rule 3 rules an unregistered content kind a
  HALT, not a UI-card default. `tests/test_ingest.py` runs both resolvers
  side by side on the same unknown string and asserts they disagree.
- Neither new module ships any rows (registrations or otherwise) — same
  discipline as `task_kinds.py`: the mapping table is code-owned in
  doc-tools, not seeded here.

## Standing constraint

No tag; v0.9.5 still Chris's word.
