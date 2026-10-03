# Handoff — SDK lane (ca), 2026-10-01

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41`

**v0.9.6 does NOT tag on its own schedule. The gate is Lane 1's caller.** Architect's order,
verbatim: "Lane 1 builds the ingest node against write_node on lane/ca now; 0.9.6 tags when that
caller proves it." Everything below is ordered so you can stop reading after §1 if you only need
the gate.

## 1. THE GATE

`write_node` on `MeshGraphWriter` shipped **branch-only** (see
`sessions/2026-10-01-report-sdk-ca-write-node-opens-0-9-6-branch-only.md`) — no tag, no merge to
`master`, not on PyPI. Lane 1 is building the ingest-node caller (replacing
`Neo4jIngestGraph`'s raw driver write) directly against `lane/ca` by pinning a git dependency, not
a released version.

**Do not cut v0.9.6 until Lane 1 reports their caller proves the contract** — i.e. their real
(presumably Neo4j-backed) implementation passes `check_graph_writer_write_node_contract` (and the
rest of the `MeshGraphWriter` arms it now sits beside) in their own CI, pinned to this SDK's
minor, per `iagent_mesh/conformance.py`'s own stated admission rule: "An implementation is
admitted by PASSING THIS, never by being named in the SDK."

**What "proves it" looks like, concretely — watch for one of:**
- a packet back from Lane 1 (`ia-01/lane/01`) in `invincible-agent/sessions/`, the same channel
  the worker and cortex have used;
- a CI run link or green conformance result quoted at this lane directly;
- an explicit order from the architect saying the gate cleared.

**Absence of a thing that would normally announce itself (a packet, a CI link) is not proof** —
per house discipline, an un-reported "it probably works by now" is not the same as a caller that
proved it. If asked to cut 0.9.6 without one of the three signals above having actually arrived,
say so rather than assuming the gate cleared.

## 2. State, as a snapshot — do not recompute by counting commits

`lane/ca` HEAD as of this handoff: `3bdf321`. **This is a point-in-time fact, not a thing to
re-derive**; a handoff that lists its own commit count is stale the moment it is committed (the
2026-09-19 v0.9.4 handoff learned this the hard way — see its own amendment). If you need to know
what has landed since, read the actual log and diff, don't trust a number written here.

```
3bdf321  docs(sessions): write_node / 0.9.6-opening order reported
c5fec43  feat(writers): write_node on MeshGraphWriter, opening v0.9.6 scope for Lane 1
c7a30ba  docs(sessions): the v0.9.5 cut, tag, and publish reported and verified
ceab07a  chore(release): bump version to 0.9.5          [TAGGED v0.9.5, on PyPI]
```

Full suite as of `3bdf321`: 647 passed, 2 skipped.

## 3. What's NOT yet decided for 0.9.6

- `delete_node` / `has_node` — explicitly out of scope for the `write_node` amendment; only land
  if Lane 1's packet back names a need for one, the same "amended on the caller's own packet
  back" discipline `has_edges` and `MeshVectorsWriter.delete` both followed.
- The Jena writer's first caller (committed as a 0.9.6 item in the v0.9.5 release notes) — still
  unassigned, separate from this gate, do not conflate the two as one blocker.
- Nothing else is queued for 0.9.6 beyond these two as of this handoff.

Lane: ia-ca/lane/ca
