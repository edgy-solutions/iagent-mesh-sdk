# Handoff — SDK lane (ca), 2026-09-23

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's opening order of this date

Answers the opening order's six rulings (a)-(f), its housekeeping, and its two reads (plus a
third, ADR-0038, asked alongside them). **Still true and still governing: no tag, no PyPI, not
cut on its own** — nothing below changes that; `over_limit`/`completeness` land as ordinary
commits on the parked branch, same as the code items in the prior overnight order.

---

## 1. HOUSEKEEPING — DONE

* **CLAUDE.md moved to master.** It landed on `lane/ca` at `06c3c5f`, which broke the branch's own
  code-tip invariant (a root `CLAUDE.md` is not one of the four v0.9.4 files). Cherry-picked to
  `master` at `e138769`; reverted on `lane/ca` at `512c7c9`. Both pushed.
* **`.mcp.json` — already resolved, not by this session.** The order asked to strip
  `forge_extension` from it; `7abfe4a` ("Removed mcp", Chris, 2026-09-20, already on `lane/ca`
  before this session started) deleted the whole file. Nothing further to do, but see §2 — this
  is why the invariant count moved.
* **`dist/` removed.** Held only the stale 0.4.0 wheel + sdist the project memory doc warns about.
  Gitignored; nothing tracked was lost.
* **Three packets, `to:` lines verified against `lane_packets.scan` directly** (ran the scanner,
  not just read the regex) — see §5.

### The code-tip invariant — RE-RUN, and it no longer reads four. Here is why, precisely.

    git diff --stat 711c6d0..lane/ca -- . ':!sessions'

now shows **seven** files, not four:

    .mcp.json                                            |   7 -   (Chris, 7abfe4a, pre-dates this session)
    iagent_mesh/__init__.py                              |  73 +-  (root-name landing + over_limit export)
    iagent_mesh/enumeration.py                           |  89 +-  (ruling d, this session)
    tests/test_every_public_name_is_reachable.py         | 154 +-  (pre-existing, from the prior order)
    tests/test_graph_manifest.py                         |  78 +-  (pre-existing, from the prior order)
    tests/test_the_enumeration_says_whether_it_truncated.py | 113 + (ruling d, this session, new file)
    uv.lock                                              |  15 +-  (pre-existing, from the prior order)

**Do not read this as the invariant failing.** The four-file count was measured at a point in the
branch's history that has since taken on two more rounds of real, ruled work: `.mcp.json`'s
removal (already landed when this session began) and this session's `completeness`/`over_limit`
build (ruling d, below). A document — or an invariant — that names a commit count is stale the
moment more ruled work lands; the prior handoff said this about itself and it is true here too.
**What stays invariant is the CLAIM, not the number**: every file in that diff traces to a named
ruling or an already-landed housekeeping commit, and nothing outside those seven appears. If a
future session runs this check and sees an EIGHTH file with no ruling behind it, that is the real
finding — not the count moving from four to seven for reasons already on record.

---

## 2. RULINGS (a)-(f)

* **(a) Root names — ACCEPTED, already landed, nothing to do.** `compose`, `json_schema`,
  `validate_dir` were already at root pre-ruling (shipped since 0.7.x, consumed by
  `agent_fleet/graph_host/main.py:43-46`) and the ruling's own "never subtract from a published
  surface" clause means they stay — that's the "three root names stay." `resolve` is the fourth
  double-exported name and stays out on both sides. "Sixteen accepted" ratifies the measured
  promoted-root count (vs. the order's original fourteen) as correct. Ruling text is in code now,
  not just in a session file: `iagent_mesh/__init__.py:125-151`,
  `tests/test_every_public_name_is_reachable.py:100-129` (`_EXEMPT`).
* **(b) `uv.lock` stale on master — ACCEPTED, already landed** at `14b0f59` before this order.
* **(c) The hand-listed slot-ref test — ACCEPTED, already landed** at `195e2dd` before this order,
  now derived from `SlotDecl.model_fields` instead of a hand list.
* **(d) `completeness` — BUILT, this session.** `EnumerateInstancesResponse` gained
  `completeness: Literal["complete", "truncated", "unknown"] = "unknown"` and
  `total_available: Optional[int] = None`, mirroring `scoped_by`'s fail-safe-default shape exactly
  — `"unknown"` because 0 of 5 fleet providers currently emit this field, and a claim this module
  might otherwise derive from `len(instances) < limit` is exactly the dishonesty `scoped_by`'s own
  docstring warns against, in the other direction. `over_limit(request, response) -> bool` seals
  `len(instances) <= limit`, the invariant nothing checked before now. Landed at `3ce0912`,
  promoted to package root alongside `unhonoured_scoping` (required a matching edit to
  `iagent_mesh/__init__.py` that the implementer correctly flagged rather than guessed past — the
  export guard `test_every_public_name_is_reachable.py` would have failed otherwise). **427
  passed, 2 skipped** on the full suite after landing (419 passed, 2 skipped before). Pushed.
* **(e) `include_referents` — ROUTED to the worker (`ia-74/lane/74`), not built here.** The fix
  (`agent_fleet/ontology_service/main.py:2084` default `True`→`False`, `:2446` made explicit
  `include_referents=True`) is fleet code, not SDK code — the file lives in `invincible-agent` and
  the Protocol import ban means ca cannot own it. Packet sent, see §5.
* **(f) `mode` vocabulary + provider obligation — DRAFTED, no code, per the ruling's own
  condition.** Widens `MeshVectors.MODES` to
  `("hybrid", "hybrid-lexical-only", "hybrid-unverified", "bm25")`, with `hybrid` earned only by a
  `nearObject(self)` retrievability witness — the same shape eo's dead-vector-space measurement
  used to catch the defect. Packet sent to the architect for read-before-code, see §5.

---

## 3. THREE READS

### (1) MeshOntology — Protocol-only. No fleet implementation, no conformance test.

`MeshOntology` (`iagent_mesh/interfaces.py:216-229`) declares `ask`/`construct`, no write half (by
design — no verified SPARQL update path). `iagent_mesh/discovery.py:44-46` declares the entry-point
group `iagent_mesh.ontology` for a downstream implementation to register against; nothing in
either repo fills it. **By contrast, MeshGraph and MeshVectors each have both**: `class Neo4jGraph`
+ `tests/test_mesh_graph_conforms.py`, `class WeaviateVectors` + `tests/test_mesh_vectors_conforms.py`
(the latter 355 lines, exercising the SDK's shared `conformance.py` harness). There is no
`mesh_ontology.py` and no `test_mesh_ontology_conforms.py` anywhere. `docs/interfaces.md:249-270`
documents the contract but gives no implementation example for it, unlike its `Neo4jMeshGraph`
walkthrough for the conformance recipe in general. This is a real gap between what the SDK
promises three named contracts and what has a second citizen behind it — one of three has none.

### (2) NetworkPolicy gap — tracked nowhere as a chart item; two corrections; now routed.

Confirmed absent from `docs/BOARD.md`, `docs/adr/`, `docs/plans/` in `invincible-agent` — as a
live backlog item it genuinely does not exist anywhere, which is what the project memory doc
already said. **Two corrections worth carrying forward past this handoff:**

1. The strict xfail this SDK's own docstring refers to (`iagent_mesh/interfaces.py:20-37`) does
   **not live in this repo**. It's `invincible-agent/tests/test_substrate_allowlist_exceptions_expire.py:173-204`,
   `test_THE_NETWORKPOLICY_MANIFEST_EXISTS`. Anyone reading the SDK docstring and searching
   `iagent_mesh/tests/` for "the test" won't find it there.
2. It IS extensively tracked as narrative record — a named ruling in
   `invincible-agent/docs/rulings/README.md:2965-2974` and several dated handoffs — just never as
   a chart/backlog item, which is the specific absence that makes it invisible to planning.

Routed to Lane 1 as a chart item; packet sent, see §5.

### (3) ADR-0038 — partially built. Not "just a yaml nothing checks."

The ADR defines a real config schema (provenance-field → Langfuse-primitive mapping, with
two-tier validation: shape at the leaf, truth at the mesh repo). **Both validators are live**:
shape validation ships in the external `provenance-telemetry==0.1.0` leaf package
(`provenance_telemetry/mapping.py`, pydantic validators rejecting unknown slots/score encodings);
the mesh-repo truth-check is `invincible-agent/tests/test_telemetry.py:75-88`,
`test_mesh_mapping_truth_check`, asserting symmetric equality between the mapping's declared
fields and what `build_trace_values()` actually emits — enforced by CI-run pytest, not a
hand-authored file nothing reads. **Still spec-only**: the `scores` row of the ADR's mapping table
(`baml_shared/telemetry-mapping.yaml:17-18` says so explicitly — scores are emitted downstream of
the entry boundary, not yet declared), and rollout stages 3-5 (doc-tools artifact-keyed tracing,
prompt-hash linkage, the OTEL migration) — no code found for any of the three in this pass, flagged
as unconfirmed-absent rather than confirmed-absent since the search wasn't exhaustive over those
specific stage markers.

---

## 4. MEASURED vs INFERRED, this session

### MEASURED

* 06c3c5f touches only `CLAUDE.md`, cherry-picks cleanly, was already pushed on both ends before
  this session (0/0 vs origin on both branches at start).
* The code-tip invariant's four-file baseline vs. today's seven, file-by-file, per §1.
* `iagent_mesh/enumeration.py`'s pre-ruling state had no `completeness`, `total_available`, or
  `over_limit` — confirmed by reading the file before delegating the build, not assumed from the
  packet describing the gap.
* Full suite: 419 passed / 2 skipped before the `completeness` build, 427 passed / 2 skipped
  after (measured by the implementer via `git stash`, and independently re-run by this session
  after the root-export fix — same 427/2 result both times).
* `lane_packets.scan`, run directly (not just its regex read) against all three new packets:
  `include_referents` packet → `addressee=74`; NetworkPolicy packet → `addressee=01`; mode-vocabulary
  packet, addressed `to: the architect` per this repo's own unbroken precedent for architect-bound
  packets → `addressee=None`, same as every prior `to: the architect` packet in `invincible-agent/sessions/`
  — the architect isn't a lane, so this is consistent with how the scanner is designed, not a gap
  in the new packet.

### INFERRED

* That `resolve` (the fourth double-exported name) staying out at root is uncontested — I read the
  ruling's "never subtract from a published surface" language and the existing `_EXEMPT` table; I
  did not find a packet specifically re-litigating `resolve` itself.
* That rollout stages 3-5 of ADR-0038 have no code — a targeted-but-not-exhaustive grep, named as
  such in §3(3).

---

## 5. PACKETS SENT (three, per the order)

    invincible-agent/sessions/2026-09-23-packet-from-ca-include-referents-ruled-fix-two-lines-in-main-py.md
        to: ia-74/lane/74 — ruling (e)
    invincible-agent/sessions/2026-09-23-packet-from-ca-mode-vocabulary-and-the-provider-obligation.md
        to: the architect — ruling (f), no code
    invincible-agent/sessions/2026-09-23-packet-from-ca-networkpolicy-gap-routed-as-a-chart-item.md
        to: ia-01/lane/01 — read (2)

All three written into `invincible-agent`'s checkout, not committed by this lane — per the
standing rule that a packet written into another lane's checkout is not this lane's to commit.

---

## 6. STANDING

* No tag, no PyPI, not cut on its own — unchanged.
* Nothing touches a shared store without Chris — unchanged, and nothing in this session did.
* `.claude/settings.local.json` is still modified, still not this session's, still untouched.
* `resolve`'s status, the `marker_is_stale` alias, and ADR-0038's `scores` slot + stages 3-5 are
  named here so they aren't lost; none is closed by this session.

Lane: ia-ca/lane/ca
