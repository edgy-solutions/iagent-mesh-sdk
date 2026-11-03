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

# RULED 2026-11-02 (architect, via Chris) — question 1 answered, question 3 reversed

> MeshData returns a handle, not rows: `resolve(initiator, urn) → MeshResult[DataRef]` where
> DataRef carries the ticket, the schema (column names + types), row-count estimate, as-of, and
> provenance; materialising is the caller's step through the client it already has (dag-tools), so
> polars never enters the SDK and the one-way dependency holds. Read-side filtering (columns,
> predicate, period) goes on the resolve as declared parameters the broker applies, so the handle
> is already scoped to what the caller may see. That is what the finance inputs contract names in
> a row. Spec that; the doc edit and the Protocol land only when engine-fin is the second caller —
> ca is right that one caller doesn't justify it, and fin will be the second this week.

This settles question 1 as **(b)**, sharpened: not a bare URI/schema pair but a named shape,
`DataRef`, with five fields —

- `ticket` — the opaque, signed/scoped handle the caller hands to its own client (dag-tools) to
  materialize. This Protocol never resolves it further; resolving it IS this call.
- `schema` — column names and types, substrate-agnostic (no polars `Schema` object crosses the
  line — a plain mapping or tuple of `(name, type_name)` pairs, decided when the Protocol is
  actually written).
- `row-count estimate` — a count, not a promise; the materializing read may differ.
- `as-of` — when the handle's scope was evaluated, same role `MeshGraph`/`MeshOntology` already
  give an as-of elsewhere in this file.
- `provenance` — who/what granted the scope, same discipline `EvidenceRef`/`GRANTED_BY_SEED`
  already carry elsewhere in this SDK.

**Question 3 (as-of/predicate pushdown) is reversed from "out of scope for v1."** It was proposed
OUT because adding a pushdown parameter this SDK cannot honor uniformly across backends looked
like `MeshResult`'s own "degrade silently" failure one level up. The ruling resolves that
differently: pushdown is not a parameter the Protocol promises to honor on the READ — it is a
parameter on the RESOLVE, applied by the broker before the handle is returned. The handle that
comes back is already scoped to columns/predicate/period; there is nothing left to silently
degrade, because nothing optional is being promised at read time. `resolve(initiator, urn, *,
columns=None, predicate=None, period=None) -> MeshResult[DataRef]` — all three declared, all three
applied by the broker, not by this SDK, before `DataRef` exists.

## Grounding "the finance inputs contract names in a row"

Read `invincible-agent/agent_fleet/finance_agent/measure_verbs.py` (ADR-0036/ADR-0053 overlay-row
mechanism) to ground this rather than guess at it. A finance MEASURE row's `inputs.state` names
quantities from a CLOSED vocabulary, `STATE_VOCABULARY` (line 90):

    program.bac, period.bcws, period.bcwp, period.acwp,
    cumulative.bcws, cumulative.bcwp, cumulative.acwp

— refused at load (`_build`, line 254) if a row names anything outside it. This is exactly the
`BCWS`/`BCWP`/`ACWP`-per-period shape the finance packet's columns already use, and exactly what
lane/01's EV-fixture spec (below) names as its own columns. The ruling's line reads as: `DataRef`'s
`schema` is the surface a measure row's `inputs.state` can point at — the handle's columns are not
an arbitrary CSV shape, they are (or must be nameable against) this closed vocabulary, which is
what makes "the finance inputs contract names [these columns] in a row" true rather than
coincidental. This is a naming/shape constraint on `DataRef.schema` for the finance case, not a new
field — noted here so the eventual `MeshData` spec's worked example doesn't drift from it.

## Worked example (prospective, not yet live)

Per `invincible-agent/sessions/2026-11-02-packet-to-architect-from-lane-01-spec-sandbox-ev-asset-
in-the-demo-location-behind-its-real-broker.md` — lane/01's `ev_fixture`: nine work packages by six
periods (NP-MERIDIAN seed's own figures, chosen so the graph and the asset must agree), columns
`program, control_account, work_package, period, BCWS, BCWP, ACWP` (fin's names), URN via
`dag_tools.inventory` (never typed literally), living in `dag_tools.user_deployment` demo mode
behind the real `iagent-dag-tools-broker` (no new pods). Access: one `policy/asset_grants.yaml` row
grants alice; bob gets no row (the refusal control).

If `MeshData` existed today, the shape would read:

    ref = mesh_data.resolve(
        initiator,                       # alice: granted; bob: not
        urn,                              # from dag_tools.inventory, never typed
        columns=["program", "control_account", "work_package", "period", "BCWS", "BCWP", "ACWP"],
        period=("2026-01", "2026-06"),
    )
    # ref.rows[0].schema  -> [("program", "str"), ..., ("BCWS", "float"), ...]
    # ref.rows[0].ticket  -> handed to CortexDataClient to materialize
    client = CortexDataClient(originator_email=initiator.require_authz_id())
    lf = client.materialize(ref.rows[0].ticket)   # name illustrative; the real method isn't built

**This is illustrative, not a verified call site.** Four items in lane/01's own spec are still
unchecked as of today (the DataHub ingestion hop; the MinIO/mintable-credential IO manager per
`docs/plans/broker-advertises-unminted-credential.md`, marked HIGH; the env-match per
`docs/plans/broker-endpoint-env-divergence.md`; the live read itself, pending Chris as alice and as
bob). Unlike the other worked examples in `docs/interfaces.md`, which are real, surveyed call
sites, this one is prospective until the fixture is live — flagged as such so it is not mistaken
for a tested contract when the doc edit eventually lands.

## What ca does now

**Nothing is built in `iagent_mesh/interfaces.py` or `docs/interfaces.md` yet.** The ruling is
explicit: "the doc edit and the Protocol land only when engine-fin is the second caller... and fin
will be the second this week." This file is the spec to build from once that trigger fires — the
method signature (`resolve(initiator, urn, *, columns=None, predicate=None, period=None) ->
MeshResult[DataRef]`), the `DataRef` field list, and the vocabulary-grounding note above are all
settled, so the moment fin is the second caller, the next step is writing the `DataRef` pydantic
model, the `MeshData` Protocol class, and the `docs/interfaces.md` section — not re-opening any of
questions 1–3.

Question 2 (the read key, `urn` opaque) and question 4 (the size gate, implementation-only) stand
as written above, unruled but non-blocking.

Lane: iagent-mesh-sdk/lane/ca
