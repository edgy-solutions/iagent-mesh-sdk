# Handoff — SDK lane (ca), 2026-09-27 (second)

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's fifth order ("Mesh* work, tonight")

**Still governing: no tag, no PyPI, not cut.** Suite **492 passed, 2 skipped** (was 476; +16
tests, 0 removed).

## 1. `mesh_explain` — BUILT AND SEALED, on `lane/ca`

New `mcp_server/mesh_explain.py`, wired into `mcp_server/server.py` as a third `@mcp.tool()`
alongside `scaffold_local_workspace`/`publish_local_to_mesh`. Calls engine-docs `POST /explain`
and always returns a `MeshResult`, never a bare string — the other two tools' `except Exception as
e: return f"Failed to ...: {e}"` is the exact anti-pattern this one does not repeat.

**Outcome mapping, read against `agent_fleet/docs_agent/main.py::explain_endpoint`, not guessed:**

| engine-docs | `MeshResult.outcome` | why |
|---|---|---|
| 200, `abstained: true` | `empty` | asked; nothing explains this subject yet — the corpus's normal state |
| 200, `pages: [...]` | `answered` | rows = the pages, whole |
| 503 | `unreachable` | reader/store not wired, or `ReaderUnavailable` — a deployment state |
| 422 / 502 / 409 | `failed` | bad request / body missing / sha mismatch (409 refuses the whole answer on purpose) |
| connection error / timeout | `unreachable` | could not even ask |
| anything unmapped | `failed` | refused to guess it means `empty` — the collapse `MeshResult` exists to end |

**The identity is a `delegate`, and honestly so.** `mesh_explain` builds
`Initiator(subject=..., kind="delegate", on_behalf_of=...)` and sends it as **informational
headers** (`X-Mesh-Initiator-Subject/-Kind/-On-Behalf-Of`), never an `Authorization` bearer —
**no mint path exists for `kind="delegate"`** (per the 2026-09-27 packet to `ia-74/lane/74`), so
sending one would be inventing a credential this SDK cannot back. Sealed:
`test_the_delegate_initiator_is_REFUSED_by_require_person` runs this tool's own identity through
`Initiator.require_person` and asserts `DelegateIdentityRefused` — proof it never quietly claims
to be a person — and `test_on_behalf_of_travels_as_a_header_not_an_authorization_credential`
asserts no `Authorization` header is sent. "Refused by the service guard" (the order's phrase) is
this: the identity is honestly non-person, provable by the same allowlist every other caller is
held to, not a new gate mesh_explain itself calls before answering.

**Config, `iagent_mesh/config.py`:** `ENGINE_DOCS_URL` (required-at-use, same `settings.require()`
discipline as `GIT_PROVISION_API_URL`). `MESH_EXPLAIN_ON_BEHALF_OF` (required, no default — a
delegate with nobody accountable is a service under another name) and `MESH_EXPLAIN_SUBJECT`
(optional, defaults `mcp:mesh_explain`) are read directly from the environment in
`mesh_explain.py`, matching `service_identity.py`'s existing pattern (identity material read at
use, never through `Settings`). `README.md` and `.env.example` updated.

**Break-on-purpose, per house rule:** swapped the 503 branch to `MeshResult.failed(...)`, reran —
`test_503_is_UNREACHABLE_a_deployment_state` went RED (`assert 'failed' == 'unreachable'`) —
restored byte-identical, reran GREEN. 16 new tests in `tests/test_mesh_explain.py`.

## 2. Reachability — what a lane worktree needs, VERIFIED not guessed

Researched via `helm/invincible-agent/templates/engines.yaml:121-134` (Service def) and
`values.yaml:597-610` (port 8100):

* Service is **ClusterIP-only** — no `LoadBalancer`/`NodePort`, no Ingress
  (`helm/invincible-agent/templates/ingress.yaml` covers cortex-ui/cortex-bff/dagster/electric,
  not engine-docs). **Not reachable from outside the cluster at all today.**
* **No `NetworkPolicy` resource exists** for it (zero matches repo-wide) — consistent with
  `[[project_networkpolicy_never_built]]`: reachability inside the cluster is by the absence of a
  restriction, not a designed-open one.
* The one documented local-dev path is `kubectl port-forward`
  (`docs/sandbox-status-report.md:76,206-210` shows the pattern for other services). For
  engine-docs: `kubectl -n <namespace> port-forward svc/<release>-engine-docs 8100:8100 &`, then
  `ENGINE_DOCS_URL=http://localhost:8100`. No devspace/Tilt/VPN config exists as an alternative.

**So: a lane worktree cannot reach engine-docs without a live port-forward to a real cluster.**
Nothing in this SDK's test suite exercises that path — `tests/test_mesh_explain.py` mocks
`httpx.post` throughout — and this handoff does not claim the port-forward has been tried, only
that it is the only documented way. That is the one thing about `mesh_explain` this lane has not
verified end-to-end.

## 3. `.mcp.json` — DRAFTED, NOT APPLIED (per the order: "a proposal until Chris says")

Chris removed `.mcp.json` themselves (`7abfe4a`, "Removed mcp") — re-adding it without asking would
be reinstating a file the user deleted, not merely a new feature flag. Proposed entry, not written
to the repo:

```json
{
  "mcpServers": {
    "iagent_mesh_devex": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"],
      "env": {
        "ENGINE_DOCS_URL": "http://localhost:8100",
        "MESH_EXPLAIN_ON_BEHALF_OF": "cnogradi@gmail.com"
      }
    }
  }
}
```

The `env` block assumes the port-forward from §2 is already running in another shell; nothing here
starts it.

## 4. Write-half proposal — FILED, not code, addressed to the architect

`invincible-agent/sessions/2026-09-27-proposal-from-ca-a-write-half-for-meshgraph-and-meshvectors.md`,
`to: the architect`. **Not committed by this lane.** Cites **five of seven** writer defects found
searching September's commit history across the registrar, doc-tools, and the backfill (more than
the order asked for, not fewer) — the two left uncited are the same named-vs-unnamed-vector-space
shape recurring a second time in the registrar, itself part of the argument. Proposes: upsert by a
caller-supplied deterministic id (never store-generated, never re-derived per-writer as doc-tools'
malformed-IRI defect did); vectors always addressed by name (never the positional/legacy insert
that silently lands in an unnamed slot — the registrar's own defect, twice); refuse-not-strip on
embed failure, with `written`/`written_without_vector` reachable only when a caller explicitly
declares a write vector-optional, never as a silent degrade. Lists four rulings owed (Protocol
shape, embedder ownership, exact outcome vocabulary, and whether this lands on `lane/ca` once
ruled) and five things explicitly left undecided.

## 5. Standing

Code-tip diff (`711c6d0..lane/ca`, excluding `sessions/`): grew from twelve files to **fourteen** —
this order added two (`mcp_server/mesh_explain.py`, `tests/test_mesh_explain.py`) and edited four
already on the list (`iagent_mesh/config.py`, `mcp_server/server.py`, `tests/conftest.py`,
`README.md`, `.env.example` — the last two newly touched, both docs/config, not logic). No shared
store touched — `mesh_explain`'s own tests mock `httpx.post`; nothing in this order ran against a
live engine-docs, Neo4j or Weaviate. `.claude/settings.local.json` still modified, still not this
lane's. Two packet/proposal files sit uncommitted by rule: the 2026-09-27 worker packet (from the
prior order) and this order's write-half proposal, both in `invincible-agent/sessions/`.

Lane: ia-ca/lane/ca
