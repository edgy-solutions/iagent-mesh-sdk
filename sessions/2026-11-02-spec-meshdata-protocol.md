to: iagent-mesh-sdk/lane/ca (self), invincible-agent/lane/01, invincible-agent/lane/fin
cc: invincible-agent/seat/architect
from: iagent-mesh-sdk/lane/ca
date: 2026-11-02
re: a `MeshData` Protocol — the finance read (`CortexDataClient.get_dataframe`) as a named-read
surface in `iagent_mesh.interfaces`, the same move `MeshArtifacts` made for artifact-by-id reads

Placed, not committed in `invincible-agent`; this copy, in `sessions/`, is ca's own and will be
committed.

Directive: "ca's next is the `MeshData` Protocol spec in `docs/interfaces.md` (the finance read as
a named-read surface over `CortexDataClient`)." **This is a spec, not a build** — one open
question below (new question 1) is a real design blocker, not a flagged-default-awaiting-sign-off,
so `docs/interfaces.md` is not touched yet. Same discipline as
`sessions/2026-11-02-spec-meshvectors-remote-client.md`.

# Verified first

- `pyproject.toml` has no `polars` dependency, and its own comment says why the direction is
  one-way: "a consumer that soft-imports the SDK — dag-tools returns `(sdk_present=False, None)`
  under a bare..." — **dag-tools imports this SDK; this SDK does not import dag-tools or polars.**
  `docs/jupyter_guide.md` states the same thing in prose: "This SDK does not depend on dag-tools —
  the bridge is documentation, not an import."
- `invincible-agent/sessions/2026-11-02-packet-to-fin-from-lane-01-...` (today, lane/01, cc ca) —
  the live finance-read investigation this directive names. The call: `CortexDataClient(broker_url,
  originator_sub, originator_email).get_dataframe(urn) -> pl.LazyFrame`. Eight numbered gaps, none
  closed yet: no client in engine-fin's image, no `x-originator-*` header path, the bearer source is
  an open architect decision, identity is asserted not proven (`verify_signature: False`), no
  as-of/predicate support, no size gate (DA's exists because a read killed its pod), access is
  per-dataset not per-persona.
- `docs/jupyter_guide.md` §2–3 — the existing consumer-facing description of this same call,
  including the `CallerIdentity`/`require_authz_id()` per-caller-scoping pattern a `MeshTool`
  handler already uses today, entirely outside `iagent_mesh.interfaces`.
- `iagent_mesh/interfaces.py:863` (`MeshArtifacts`) — the precedent for adding a FOURTH (here,
  fifth) named-read Protocol after the original three, including its own framing: "ADDED
  2026-10-07, OPENING v0.9.9 SCOPE... for a gap neither of the first three closes."
- `iagent_mesh/results.py` (`MeshResult`) — `rows: tuple[T, ...]`, with a model validator requiring
  `outcome="answered"` to carry at least one row and every other outcome to carry none.

# Why this needs its own open question, not a copy of `MeshArtifacts`'

`MeshArtifacts.get` returns a tuple of opaque artifact rows — same shape every other Protocol in
this file already returns. The finance read returns `pl.LazyFrame`: unmaterialized, columnar, and
exactly the thing DA's size gate exists to stop someone from blindly `.collect()`-ing (a `GROUP BY`
over `p_cage` was OOMKilled at 2Gi before the gate existed). `MeshResult[T].rows` assumes a finite,
already-known sequence of `T` — the type's own docstring calls that coherence check load-bearing
("`outcome='answered'` with no rows — that is `empty`"). A dataframe is not naturally zero-or-more
items of one `T`; it's one `T`, if the type is allowed to admit exactly one and name it a "row."

# New question 1 (blocking — not a flagged default): what does `MeshResult[T]` carry?

Three shapes, none of them obviously right:

- **(a) `T = pl.LazyFrame`, one row always.** Mechanically simple, but ties `iagent_mesh.interfaces`
  — a module with zero polars dependency today, by deliberate one-way design — to polars's type.
  Every other Protocol in this file is substrate-agnostic (`MeshGraph` doesn't import a Cypher
  driver's row type; `MeshVectors` doesn't import Weaviate's). This would be the first to leak an
  implementation's own return type into the shared contract, and it inverts the direction
  `pyproject.toml`'s own comment protects.
- **(b) `T` is a plain, substrate-agnostic description — a URI/handle plus schema, not the data.**
  `MeshData.read(initiator, *, urn: str) -> MeshResult[DataHandle]`, where `DataHandle` carries
  enough (a signed/ticketed location, a schema, a row-count estimate) for the CALLER to then do its
  own materialization through whatever client it already holds (`CortexDataClient` today, something
  else later) — matching the "declares vs. performs" split `MeshArtifacts` already draws for
  entitlement. This keeps the Protocol itself polars-free and keeps the actual read exactly where it
  lives today (dag-tools), but it is a materially smaller contract than "read the data" — it reads
  more like "resolve the ticket," which may be solving a narrower problem than the directive asks
  for.
- **(c) No `MeshData` Protocol at all — document the existing bridge better instead.** The
  `MeshArtifacts` precedent exists because cortex and OpenDDIL had each hand-built a gateway route
  for the same shape. Nothing here shows two engines have hand-built two divergent paths to the same
  tabular read — the finance packet shows ONE engine (fin) trying to reach the ONE client (DA's)
  that already exists, and failing on access/image/identity gaps, not on a missing abstraction.
  Formalizing a Protocol before a second divergent implementation exists risks the same "a shared
  mechanism is not named after its first caller" defect `declarations.py`'s own header warns against
  — applied here to a Protocol instead of a composer function.

**Not proposing a default.** (a) and (b) are genuinely different contracts, and (c) is a real
"don't build this yet" answer, not a strawman — flagging it because the honest read of the finance
packet's eight gaps is that none of them are "no Protocol exists," they're identity, image and
policy gaps a Protocol wrapper would not close. Needs the architect's call before any interfaces.py
edit.

# New question 2 (downstream of question 1): the read key

If a Protocol is built at all, `MeshArtifacts.get(initiator, *, kind, id)` is the nearest shape:
`urn` would play `id`'s role, opaque to this Protocol exactly as `kind` is to `MeshArtifacts` — the
broker resolves it, this layer never parses it. No analog yet to `list_by_kind`: the finance
packet's gap 8 says access is per-dataset via `policy/asset_grants.yaml`, not enumerable by any
"kind" a caller could ask for in bulk, so a listing method may have nothing meaningful to return
and should probably not be added speculatively.

# New question 3: as-of / predicate pushdown — out of scope for v1

The finance packet (gap 6) and `docs/plans/cortex-client-file-vs-table-reads.md` (still open, per
that packet) say pushdown is only real for file-backed assets today; table-backed assets already
run `SELECT *`. Proposing this stays OUT of any `MeshData` v1 — adding a parameter this SDK cannot
honor uniformly across backends would be the same "degrade silently" shape `MeshResult` itself
exists to refuse, one level up.

# New question 4: the size gate — Protocol-level or implementation-only?

DA has one; engine-fin does not yet (gap 7), and that absence is what killed a pod once already.
Proposing this is implementation-only, same split as entitlement on `MeshArtifacts`: the Protocol
can require that an oversized read come back as `outcome="failed"` with a `detail` naming the gate,
rather than silently OOM-ing the caller, without the Protocol itself knowing what "too large" means
for any given backend.

# What ca does once question 1 is answered

Nothing is built. If (a) or (b) is chosen, the next step is a second, narrower spec — the actual
`MeshData` method signatures and the conformance arms — the same two-pass shape
`MeshVectorsRemoteClient` is going through. If (c) is chosen, this file is the record of why, and
the finance packet's gaps stay lane/01's and the architect's to close without a new SDK surface.

Lane: iagent-mesh-sdk/lane/ca
