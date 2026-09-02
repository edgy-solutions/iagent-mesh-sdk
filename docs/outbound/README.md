# Outbound patches — for the invincible-agent lane to apply

Patches against `invincible-agent`, generated from this repo because the packets are that
lane's files. **Not applied from here**: `docs/plans/` had live uncommitted work in it when
these were made (`engine-f-archetype-bindings.md` modified, plus an untracked new item), so
writing into that tree from this lane could have collided with work in progress.

```bash
cd /path/to/invincible-agent
git apply --check docs/../../iagent-mesh-sdk/docs/outbound/*.patch   # dry run
git apply         /path/to/iagent-mesh-sdk/docs/outbound/*.patch
```

Both were verified with `git apply --check` against the live tree, and one was applied and
reverted to confirm the result. A `trailing whitespace` warning on `blocked-on: ` is expected —
it matches the existing convention in these files.

## What each says, and why they differ

| patch | disposition |
|---|---|
| `sdk-blocking-sync-handlers.patch` | **status: closed.** Both rulings answered; all four acceptance criteria sealed. |
| `sdk-discards-caller-identity.patch` | **status: UNCHANGED (open).** The SDK blocker is gone, but the item's own step 3 is in dag-tools and is not done. |

### Why the second one is not closed

Read against the packet's own Order of Work, steps 1, 2, 4, 5 and 6 are delivered in SDK
v0.4.0. **Step 3 is not, and it is in `dag-tools`:** `CortexDataClient` still has no `caller=`
parameter, no contextvar read, no `CORTEX_USER_TOKEN` rung and no opt-in service identity
(verified against `dag_tools/cortex_data/client.py` at `61cbfa9`).

That has two consequences the patch states rather than glosses:

* **Acceptance 3 is vacuously true, not satisfied.** "`CORTEX_USER_TOKEN` on an agent pod
  changes nothing" holds only because nothing reads that variable. The designed property — the
  request's caller OUTRANKS it — does not exist, so it cannot be relied on the moment that rung
  is added.
* **Acceptance 4 is partial.** `require_authz_id()` makes an unresolved caller loud inside a
  handler, but a bare `CortexDataClient()` in that same handler still resolves to the service
  **silently**. The packet's "rung 3 must be loud" is undelivered.

Whether the packet closes at the SDK boundary or spans both repos is a scope ruling with
`owner: human`. The SDK lane has no standing to make it, so the status is left alone and the
question is put in `blocked-on:`.

## The wake condition, in both patches

**`v0.4.0` (`09d7326`) is local — not pushed, not on `origin`, not on PyPI.** Every consumer
still resolves `iagent-mesh @ git+...@v0.3.1`.

So for ADR-0046 §8.5 the checkable event is the **pin bump** across the 13 `pyproject.toml`
files and their `uv.lock` entries — not the existence of a tag. A tag that exists locally is a
fix that exists nowhere downstream. Both patches say so, and both say this file gets updated
again when the SDK is actually pushed and published.

Read strictly, §8.5's *"both defects close"* is **not met**: one is closed, one is half closed.
