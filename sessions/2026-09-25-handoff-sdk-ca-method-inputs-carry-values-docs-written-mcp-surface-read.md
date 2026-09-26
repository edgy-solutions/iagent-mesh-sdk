# Handoff — SDK lane (ca), 2026-09-25

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's second OVERNIGHT order

**Still governing: no tag, no PyPI, not cut.** Suite **463 passed, 2 skipped**.

## 1. `MethodBlock.inputs` carries values — BUILT

`inputs: list[MethodInput]`, `MethodInput(name, value: bool|int|float|str, unit: str|None)`;
`bound: float|None` was already so. The bare-name form is now refused, not coerced (tested).
**"Nothing consumed the list[str] form" is measured for this checkout:** a repo-wide search of
`invincible-agent` finds no `MethodBlock`/`producer_sha`/`bound_defaulted`. Not measured: any
uncommitted code in the worker's worktree. Reconcile packet, `to: ia-74/lane/74`:
`invincible-agent/sessions/2026-09-25-packet-from-ca-methodblock-inputs-now-carry-values.md`
(scanner reads `addressee=74`; not committed by this lane). Two choices of mine there: `value` is a
JSON scalar that keeps its type; `unit=None` is "not stated", not dimensionless.

## 2. `docs/interfaces.md` — WRITTEN

MeshOntology's contract and its guarantees (§4); a new "Ontology implementations: one extra check"
subsection (§6) with the fixture the implementer supplies; a new §8 on `MethodBlock`; quick
reference is now §9 (no inbound references to the old number). The `MethodBlock` example was
executed, not just written. The docs say plainly that the ontology arm has **no implementation
behind it** and that `method` is unreleased.

## 3. READ ONLY — the MCP surface that exists, and what exposing `mesh:explain` + registry reads would take

**Nothing was built.**

### What exists

`mcp_server/server.py` (71 lines, `FastMCP("iagent_mesh_devex")`, stdio via `mcp.run()`) exposes
**two tools, both provisioning, neither a mesh read**: `scaffold_local_workspace` (renders a
template into a directory, then runs `git init` / `git add .` / `git commit` there) and
`publish_local_to_mesh` (POSTs to `GIT_PROVISION_API_URL`, pushes the workspace to a git remote).
Nothing in it calls `mesh:explain`, the registry, or any `MeshGraph`/`MeshOntology`/`MeshVectors`
operation. It ships in the wheel (`pyproject.toml` `include`), `mcp>=1.0.0,<2` is a hard
dependency, and `README.md`/`AGENTS.md` describe it as the IDE scaffolding path. The `.mcp.json` that
registered it for this repo was deleted by `7abfe4a` (2026-09-20), so **no lane worktree currently
launches it** — it is reachable only if a session adds a server entry itself.

### Its auth

**None per caller.** `scaffold_local_workspace` has no auth at all. `publish_local_to_mesh` reads
`settings.MESH_DEV_TOKEN` (env) and sends it as `Authorization: Bearer` to the provisioning API only;
the token is one shared value with no notion of who is asking. The guard is an `assert`, which
Python strips under `-O`. The server never forwards an identity to any mesh service. So the surface
has **no answer to "who is asking"** — the question every mesh read is required to carry
(`Initiator`, service identities refused).

### Three things in it a new tool must not copy

1. **Failure is returned as a success-shaped string.** Both tools `return f"Failed to ...: {e}"`
   from a bare `except Exception`. A caller gets a `str` either way — the exact collapse
   `MeshResult` exists to end (outcome states, `bool()` raises). A mesh-read tool must return the
   four outcomes, not prose.
2. **`git add .`** in `scaffold_local_workspace` — inside a freshly created scaffold directory, so
   it is not the WIP-sweeping hazard, but it is the pattern this lane is barred from in shared trees.
3. No timeout on the `subprocess.run` git calls (a hung `git` hangs the tool). The `httpx.post` sets
   none explicitly and so takes httpx's default; a new tool should state its own.

### What exposing them would take

The two targets are already HTTP endpoints, so an MCP tool would be a thin client, **not** a driver
or a `Neo4jGraph` (the SDK holds no substrate client; that ban applies here too):

* **`mesh:explain`** → `POST /explain` on engine-docs (`agent_fleet/docs_agent/main.py:307`),
  body `{fn: "explain", params: {subject}}`. Returns a list of pages (always a list), 422 on a
  missing `subject`, 503 reader/store unwired or unavailable, 502 body missing, **409 sha
  mismatch — the whole answer refused**, and an `abstain` payload when nothing explains it.
  Those are distinct states; the tool must preserve them (503 ≠ abstain is the stated point of the
  engine).
* **registry reads** → `GET /personas` and `GET /domains` on engine-o
  (`agent_fleet/ontology_service/main.py:3934,3955`). `MeshGraph.registry()` is the Protocol
  operation, but **it needs an implementation in-process** (`Neo4jGraph`, fleet-side); an SDK-side
  MCP tool cannot call it without a driver, so it goes through these routes. **They return neither
  a `MeshResult` nor an outcome** — whether a store outage on `/domains` surfaces as an error or
  as an empty list is unverified (below), and the tool must not render an outage as an empty list.

What that needs, in order of where the real cost is:

1. **An identity decision (the hard part, and not this lane's).** Both engines mount
   `make_transport_auth_dependency` app-wide, currently **OBSERVE** (logs, refuses nothing) with a
   planned flip to REQUIRE (`[[transport-flip]]`). So an unauthenticated call *works today* and will
   stop working on the flip. A lane worktree is a non-human actor; the SDK's rules are that a
   service identity is refused at the boundary and that an identity is carried opaque from one
   claim. So the tool needs either **the operator's own per-user token** passed through from the
   lane's environment (attributable, and correct), or a **service identity that a ruling
   explicitly admits for these two reads**. `MESH_DEV_TOKEN` is neither and should not be reused.
   This is an architect ruling, not an SDK choice.
2. **Reachability.** Both are in-cluster services; nothing in the SDK settings names a base URL
   for either (`config.py` carries only git/provision fields). A lane worktree needs settings for
   two URLs plus a route to them (port-forward or ingress) — and the recorded NetworkPolicy gap
   means that route is currently unrestricted rather than deliberately open.
3. **The tool code**: two `@mcp.tool()` functions, `httpx` with an explicit timeout, mapping
   HTTP status to the four outcomes (200→answered, abstain→empty, 5xx/timeouts→failed/unreachable),
   returning a structured result rather than a `str`. Small — on the order of the existing file.
4. **Registration per worktree**: a `.mcp.json` entry (removed in `7abfe4a`), so it must be
   re-added deliberately and per lane.
5. **A seal, not just code**: a test that the tool returns `failed` — not an empty answer — on a
   5xx, proven RED by breaking it, per the house rule. Without it this would be the string-return
   pattern again.
6. **Ship path**: SDK code, so it is v0.9.4-or-later and unreleased until cut → pin.

### Not verified (named so they are not read as clean)

* Whether `/personas` / `/domains` distinguish an outage from an empty registry — I read the route
  bodies, not `fetch_active_personas`/`fetch_active_domains`.
* Whether either engine is reachable from a developer workstation at all.
* The response shape of `mesh:explain` beyond the status codes above (I read the error paths, not
  `explain_mod.explain`'s output).
* Whether `/explain` is subject to entitlement filtering per caller — nothing in the handler reads
  `current_caller()`.

## 4. Standing

Code-tip diff (`711c6d0..lane/ca`, excluding `sessions/`): now twelve files — adds `docs/interfaces.md`
to last handoff's eleven; each traces to an order. No shared store touched.
`.claude/settings.local.json` still modified, still not this lane's.

Lane: ia-ca/lane/ca
