# Handoff — two defects in `MeshTool.execute()`, and why they are one job

> ## ✅ RESOLVED in 0.4.0 (2026-08-27)
>
> Both findings fixed together, in one change to `route_handler`, as this document required.
>
> * **Finding A** — a parameter annotated `CallerIdentity` receives the invoker;
>   `current_caller()` reads the same identity from a request-scoped `ContextVar` with no
>   parameter. `CallerIdentity.require_authz_id()` is the fail-closed read accessor: it raises
>   rather than returning the `None` that silently becomes a service read.
> * **Finding B** — sync handlers run via `anyio.to_thread.run_sync` under an explicit
>   `contextvars.copy_context()`, so the doc's threading promise is now true *and* A's contextvar
>   survives into the worker thread.
>
> **Both rulings were answered by enumeration, not preference.** The handler census the document
> demanded returned **zero** `MeshTool.execute()` handlers in invincible-agent (and zero
> `MeshTool` / `MeshClient` call sites at all) — so the population holding retroactively-broken
> sync handlers was empty, and fixing the code carried no migration debt. Ruling 1 → fix the
> code. Ruling 2 → the count is zero; the five in-repo templates all use the unchanged
> single-parameter form.
>
> **The interaction this document predicted was reproduced, not assumed.** Implementing B with
> `loop.run_in_executor` passes every threading test while `current_caller()` reads `None` inside
> the recommended handler style. That is why the acceptance criterion below is a test named
> `test_THE_COORDINATION_TEST_...` — it is the only one that fails in that configuration.
>
> Tests: `tests/test_caller_identity_reaches_handler.py`,
> `tests/test_sync_handlers_do_not_block.py`, `tests/test_per_user_read_end_to_end.py`,
> `tests/test_cortex_data_client_contract.py`. Each fix was broken on purpose, shown red for its
> own reason, and restored.
>
> **Found while fixing these** (and fixed): `execute()` read the handler's annotation raw, so any
> tool module using `from __future__ import annotations` 422'd on *every* request with
> `'str' object is not callable` — see `tests/test_postponed_annotations.py`.
>
> Bridge to the data plane is `originator_email=caller.require_authz_id()` — dag-tools'
> `CortexDataClient` takes a string subject, carried opaque, so employee-id deployments work
> unchanged. `caller=` was not adopted because that parameter does not exist in dag-tools yet;
> `test_cortex_data_client_contract.py` watches its real source and goes red when it appears.

**To:** whoever owns `iagent-mesh-sdk`
**From:** the ADR-0044 / mesh-read session, 2026-08-27
**Both findings are in `iagent_mesh/core.py`, in the same function.**

Plan items (invincible-agent `docs/plans/`, on `docs/BOARD.md`):
`[[sdk-discards-caller-identity]]`, `[[sdk-blocking-sync-handlers]]`.

---

## Read this first: they touch the same seam, so sequence them

Both fixes change `MeshTool.execute()`'s `route_handler`. **Two uncoordinated fixes to one
function is how it grows a third defect**, and in this case they interact directly:

- Fix A puts a `CallerIdentity` in a request-scoped `ContextVar`.
- Fix B moves sync handlers off the event loop onto a thread.
- **`asyncio.to_thread` copies the context. `loop.run_in_executor` does not.**

Do B with `run_in_executor` and A's contextvar reads `None` inside **exactly the handler style
the quickstart recommends** — and without A's fail-closed rule, that read lands on the service
identity, silently, in the most common case. Two correct-looking fixes producing a
cross-tenant read.

Do them together, or A then B with B's mechanism chosen for A.

---

## Finding A — a tool cannot learn who invoked it

**`core.py:180`** registers the auth dependency at APP level:

```python
dependencies=[Depends(make_transport_auth_dependency(component=name))],
```

`make_transport_auth_dependency` does the right thing — it returns a `CallerIdentity` whose
`authz_id` is documented as *"the ONLY field an authorization decision may key on."* But
**FastAPI discards an app-level dependency's return value.** It is not injectable into a route,
never reaches `request.state`, and `route_handler` does not ask for it.

Then **`core.py:440`**:

```python
return func(input_data)
```

The handler receives the validated input model and nothing else.

**So the caller is computed, logged, and thrown away** — one frame before anyone could use it.

### What that forces

A tool author has nothing to put here:

```python
client = CortexDataClient(originator_email=???)
```

Their only working option is a bare constructor, which resolves to the **service identity**. So
**every user of that agent reads with the service's entitlements** — the confused deputy the
platform's own chart comment warns about on `CORTEX_CLIENT_ID`.

**It fails invisibly.** An agent reading as the service *works*. Rows come back, nothing errors,
no test fails. The only symptom is that every user sees data entitled to the service.

**Existence proof:** Engine DA does not get the caller from the SDK. It pulls `user_email` off
the request payload (`agent_fleet/data_analyst/main.py:271`) because the supervisor threads it
manually. The one agent doing per-user reads correctly had to route around the SDK.

### The target

```python
@app.execute()
def detect_anomalies(data: AnomalyInput, caller: CallerIdentity) -> AnomalyOutput:
    client = CortexDataClient(caller=caller)
```

…and better, with a contextvar, no parameter at all:

```python
client = CortexDataClient()          # notebook, pipeline, agent handler — identical
```

**The resolution order matters more than the mechanism, and it is the part to get right:**

> 1. explicit `caller=` — override, for tests. Wins over everything.
> 2. the request-scoped contextvar — the agent case.
> 3. `CORTEX_USER_TOKEN` — per-process user identity (notebook).
> 4. service identity — **opt-in only.**
>
> **Inside a request, failure to resolve RAISES.** It never falls through to 3 or 4.

**Why 2 must outrank 3:** everyone writing this by hand reaches for

```python
return os.environ['CORTEX_USER_TOKEN'] if 'CORTEX_USER_TOKEN' in os.environ else caller
```

which works in all three contexts today — **only because that var happens to be unset on agent
pods.** Set it once for debugging and every request silently reads as one user, with code that
still looks correct. A confused deputy arriving via a *config* change, with nothing to review.

Steps 1 and 2 ship together. The contextvar without the fail-closed rule just relocates the
silent service-read from "author forgot `caller=`" to "contextvar was empty for a reason nobody
noticed."

---

## Finding B — the quickstart promises a background thread that does not exist

**`core.py:438`**:

```python
if inspect.iscoroutinefunction(func):
    return await func(input_data)
return func(input_data)          # no threadpool
```

**`docs/jupyter_guide.md`**:

> **Use standard `def` (Recommended):** If you are crunching Polars DataFrames
> (`df.collect()`), stick to standard `def`. **We will execute it safely in a background
> thread.**

`grep -rn "run_in_threadpool\|to_thread\|run_in_executor" iagent_mesh/*.py` → nothing.

A recommended handler doing `df.collect()` holds the event loop for its duration. Every other
request to that tool, including health probes, waits.

**The doc recommended the failing path for the heaviest workload**, so authors who complied are
worse off than authors who ignored it.

### Two rulings, neither of them technical

1. **Fix the code or fix the doc?** Threading makes every existing sync handler retroactively
   correct — and changes execution semantics for handlers written assuming single-threaded
   module state. Correcting the doc makes them retroactively wrong and obliges migration. The
   choice decides **which population currently holds broken code.**
2. **Who audits existing handlers, and how many are there?** Neither option can be sized
   without a count. Enumerate before choosing — a remembered list of "the tools we know about"
   is how the sixth one breaks.

---

## Acceptance for the pair

- A tool handler can name its invoker; a read inside it authorizes as **that person**.
- Two different users invoking the same agent against the same asset get **different rows**.
- `CORTEX_USER_TOKEN` set on an agent pod changes nothing — the request's caller outranks it.
- Reading as the service requires saying so.
- A sync handler doing a multi-second `collect()` does not delay a concurrent request.
- **If threaded: a `ContextVar` set by the auth dependency is readable inside a sync handler.**
  This is the test that proves the two fixes were coordinated.

## Context worth having

The mesh's read path was hardened today (invincible-agent ADR-0044, dag-tools 0.3.2): routing
tickets now carry only broker-minted credentials, scoped to the asset and expiring with the
access window. That closed *what a caller is handed*. Finding A is *whether an agent can say
who is asking* — and it is the blocker on the notebook→agent path, which is where the users
are actually heading.

Not filed by an agent unilaterally because both rulings are blast-radius questions, not
technical preferences.
