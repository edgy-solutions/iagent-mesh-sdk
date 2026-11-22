# DevEx Hub: Dashboard & API-Layer Authorization (DRAFT)

> **Status: draft.** This guide documents a pattern the architect approved for write-up on
> 2026-11-21; it has not shipped against a first real dashboard or API-layer instance yet. One
> question central to the dashboard half — §3 below — is recorded as **open**, not answered.
> Treat this as the current best answer, not a settled contract, until that question closes and
> this notice is removed.

A notebook cell (see [`jupyter_guide.md`](jupyter_guide.md)) runs once, for one person, in one
process the person themselves started — its `CallerIdentity` resolves once and the cell is done.
A dashboard or an API layer is a long-lived, multi-tenant *server*: many people's requests pass
through the same running process, often concurrently. This guide is for that second route — an
IDE-based service author building a dashboard panel or a REST route, not someone prototyping in a
notebook cell.

## 1. One decision point, unchanged

Everything here composes with the notebook pattern rather than replacing it:

- **One decider.** Topaz decides RLS/column masking on every per-user data read; nothing in this
  guide introduces a second decider.
- **One opaque subject.** `CallerIdentity.authz_id` / `current_caller()` is the *only* channel a
  per-user read may key on — never parsed, carried verbatim end to end.
- **Fail closed, not fall back.** `require_authz_id()` refuses an unresolved caller rather than
  falling back to the tool's own service identity.
- **Declare your posture.** `caller: CallerIdentity` parameter, or `current_caller()` plus
  `@app.execute(caller_scoped=True)`, or an explicit `caller_scoped=False` — see
  [`jupyter_guide.md` §3](jupyter_guide.md#3-the-anatomy-of-a-domain-node-a-conceptual-look).
- **The bridge is documentation, not code the SDK owns.** `CortexDataClient` lives in dag-tools;
  the SDK states the contract (`originator_email=caller.require_authz_id()`) without depending on
  the package that consumes it.

This is not a new mechanism to build. `make_transport_auth_dependency()` and `current_caller()`
already give every mesh node mounted as a FastAPI app a *per-request* caller: the `ContextVar` is
set inside Starlette's own per-request copied context, which is why two concurrent requests
through one process already read two different callers today. A dashboard or an API layer is,
for this purpose, simply another FastAPI-mounted surface — the pattern is "mount the same
dependency, resolve the same way, per route," not a parallel identity stack built to fit a
dashboard's shape.

## 2. Pattern for an API layer

An API layer is a mesh node (or a set of them) reached directly over HTTP/REST instead of only
through Engine O / the supervisor. Nothing about "directly" changes the authorization contract:

```python
from fastapi import FastAPI, Depends
from iagent_mesh.transport_auth import make_transport_auth_dependency, CallerIdentity

app = FastAPI()
auth = make_transport_auth_dependency(component="sample-api")

@app.get("/v1/items")
async def list_items(caller: CallerIdentity = Depends(auth)):
    client = CortexDataClient(originator_email=caller.require_authz_id())
    ...
```

This is the notebook pattern's §3 block, verbatim, mounted at an HTTP route instead of invoked by
the supervisor. The declaration table applies unchanged. No second auth stack, no API-key concept
that bypasses `verify_bearer` — an API consumer authenticates with the same bearer a mesh caller
would carry, checked against the same `MESH_JWT_ACCEPTED_ISSUERS` / `AUDIENCES`.

## 3. Pattern for a dashboard tool

A dashboard adds one real wrinkle the notebook and the bare API layer don't have: a human sits in
a browser with their *own* login session against the dashboard (cookie, dashboard-issued session
token), which is **not** the same object as a mesh bearer.

> **Open question — not answered here.** How does a dashboard's own session exchange for a mesh
> bearer? Two shapes, neither decided:
>
> - **(a)** the dashboard's login flow mints a mesh-accepted token itself (Keycloak/PingSSO
>   issues it directly; the dashboard just forwards the `Authorization` header it already has) —
>   keeps Topaz as the sole decider with zero new code.
> - **(b)** the dashboard exchanges its own session for a short-lived mesh token via a
>   token-exchange call — more moving parts, needed only if the dashboard's own session issuer is
>   not already one of `MESH_JWT_ACCEPTED_ISSUERS`.
>
> (a) is strictly simpler and is the leaning default unless something about a dashboard's actual
> login stack rules it out. This needs confirmation against whichever dashboard is the first
> real instance of this pattern — flagged for 74 / the architect, not assumed here.

Once a per-request bearer is in hand (by whichever answer that open question gets), each panel's
own data fetch follows the identical per-user discipline:

```python
@dashboard.panel("/panels/sample-metric")
async def sample_metric_panel(caller: CallerIdentity = Depends(auth)):
    client = CortexDataClient(originator_email=caller.require_authz_id())
    lf = client.get_dataframe(SAMPLE_DATASET_URN)
    ...
```

**The invariant worth stating by name, because it's the shortcut a dashboard author is most
likely to reach for:** one dashboard-wide client built at startup, reused across every viewer's
panel, is the service-identity defect — the exact failure the notebook guide's §3 already warns
against, just easier to fall into in a dashboard's longer-lived process. Always resolve the
client per request, from `Depends(auth)`, never from a module-level instance.

## 4. Relaying onward from a panel or route

If a dashboard panel or an API-layer route itself needs to call *another* registered provider on
the caller's behalf within the same request, it reaches for
[`caller.require_bearer_for_relay()`](../iagent_mesh/transport_auth.py) rather than a
dashboard-specific mechanism. This guide's job is getting a correct, per-request
`CallerIdentity` onto a dashboard/API route at all; `require_bearer_for_relay()`'s job is what a
handler does with it when it must relay onward.

## 5. Open questions, recorded rather than decided

1. **The session-exchange question in §3** — the central open item in this guide.
2. **Does an API layer need its own `component=` convention** for
   `make_transport_auth_dependency`, distinct from a mesh node's, so the exempt-probe-path gauge
   and the posture logs can tell "API layer" traffic apart from "mesh node" traffic? Likely yes,
   unproven until a first real API layer exists to check it against.
