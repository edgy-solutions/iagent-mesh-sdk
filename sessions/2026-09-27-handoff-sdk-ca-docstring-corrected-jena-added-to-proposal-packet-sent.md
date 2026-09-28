# Handoff — SDK lane (ca), 2026-09-27 (third)

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's sixth message (ruling +
Chris's direct notes)

**Still governing: no tag, no PyPI, not cut.** Suite **492 passed, 2 skipped**, unchanged by this
segment's edits (docstrings only, no logic touched).

## 1. `MeshOntology`'s false write-blocker — CORRECTED, committed, pushed

The architect's ruling: the docstring's "no verified route" paragraph
(`iagent_mesh/interfaces.py`) was measured false against sandbox Fuseki (7f's report,
`doc-tools/sessions/2026-09-27-report-7f-mesh-jena-update-route-and-writer-inventory.md`) — `POST
update=<sparql>` to `/{dataset}/update` returns 200; the `endpoint.replace("/sparql", "/update")`
substitution the old text blamed doesn't exist in any live code (removed 2026-09-14). Corrected in
three places, all carrying the same stale claim: `iagent_mesh/interfaces.py` (the docstring
itself), `tests/test_interfaces.py` (the test's own explanatory docstring), `docs/interfaces.md`
(the public contract blockquote) — the latter two found by grepping for the false phrases after
fixing the first, not asked for by name. The GET-404 trap (`GET /ds/sparql` 404s, `POST` to the
same path 200s) is named explicitly so the false conclusion can't be re-derived from the same
symptom. The honest remaining reason for no write half: no ruling yet on SDK write shape or graph
scoping — not a broken route. Committed `52cc555`, pushed.

## 2. Write-half proposal — Jena-first section added, per the ruling

"The write half then goes into ca's proposal with Jena first, as 7f recommends." Added new §1a to
`invincible-agent/sessions/2026-09-27-proposal-from-ca-a-write-half-for-meshgraph-and-meshvectors.md`
(title widened to `MeshGraph`, `MeshVectors`, **and `MeshOntology`**): Jena/`semantic_assets.py:531`
as the first production caller a shared writer replaces (one call site vs. Neo4j's two and
Weaviate's three), the three-plugin default-graph defect (`compliance.py:155`,
`maintenance.py:330`, `manufacturing.py:423` — bare `INSERT DATA` landing outside any named graph,
invisible to the mesh resolver) as a live defect grounding "the writer must own graph scoping,
structurally, not by convention," and the existing log-not-raise failure path at the one call site
as the same "wrote nothing, said nothing" shape as defect #1. Weaviate confirmed last (three call
sites, three vector-argument shapes, one deliberate refusal to preserve exactly);  Neo4j the middle
case. §7/§8 updated to reflect that *which store first* is now settled; the rest of migration
sequencing is not. **Not committed by this lane** (addressed to the architect, per packet
convention) — still sitting in `invincible-agent/sessions/`, uncommitted, as it was before this
segment.

## 3. Authorization packet to 7f — sent

`doc-tools/sessions/2026-09-27-packet-to-7f-graph-scoping-and-pr-corrections-authorized.md`,
`to: doc-tools/lane/7f`, relaying the architect's exact text: graph scoping into the shared
`execute_update` writer (own PR, not merged, sealed on the three unscoped plugins) and one-line
corrections to PR #15/#16 bodies — both 7f's/the architect's actions in `doc-tools`, **not
performed by this lane**. Also noted, for 7f's context: the write-half proposal's §1a narrows to
"don't regress it" if 7f's graph-scoping PR lands first. **Not committed by this lane** (their
repo, their commit).

## 4. The BFF 401 — documented where the tool lives, not fixed

Chris, directly: engine-docs sits behind the BFF's bearer check; `mesh_explain` sends no
`Authorization` header (no mint path for `kind="delegate"` exists), so the **first real,
non-mocked call from a lane worktree will 401** — one layer before `/explain` is ever reached, by
the gateway, not by engine-docs' own logic. This is expected, not a defect in the tool. Named
explicitly in `mcp_server/mesh_explain.py`'s module docstring (new paragraph, no behavior change,
committed `ff52820`, pushed) so the next reader doesn't mistake the OBSERVE-posture note above it
for "this call will succeed against a live cluster." The actual fix is out of scope here: a
Keycloak client-credentials client **per delegate** (this lane, a future edge agent), with
`on_behalf_of` becoming a claim the gateway *records* and never gates on — "the next SDK/fleet item
once the proposal is read," per Chris, and also named as what the OpenDDIL edge agent will need.
Not started; no ticket filed by this lane — flagging it here and in project memory is as far as
this segment goes.

## 5. Standing

Two new commits on `lane/ca` this segment, both docstring/docs-only, both pushed:
`52cc555` (interfaces.py + test_interfaces.py + docs/interfaces.md correction),
`ff52820` (mesh_explain.py BFF-401 addendum). No logic changed; full suite reran green (492/2)
after the interfaces correction, and the mesh_explain suite alone reran green (16/16) after its
addendum. `.claude/settings.local.json` still modified, still not this lane's, left unstaged in
both commits (verified via `git status --porcelain` before staging each). Two uncommitted
packet/proposal files remain by rule, now three: the prior order's worker packet
(`invincible-agent/sessions/`), the write-half proposal with its new §1a (`invincible-agent/sessions/`),
and this segment's packet to 7f (`doc-tools/sessions/`) — none committed by this lane.

**What this lane did NOT do, on purpose:** the PR #15/#16 body corrections and the graph-scoping PR
itself. Both are 7f's/the architect's actions in `doc-tools`; this lane's role was to relay the
authorization verbatim, which it did.

Lane: ia-ca/lane/ca
