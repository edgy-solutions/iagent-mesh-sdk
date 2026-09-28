# Handoff — SDK lane (ca), 2026-09-26

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's third OVERNIGHT order

**Still governing: no tag, no PyPI, not cut.** No SDK code changed this order; suite unchanged (**463 passed, 2 skipped**,
last run at `84d6f58`, not re-run — nothing in the package moved).

## 1. TS mirror — PACKETED to cortex

`cortex-ui/sessions/2026-09-26-packet-from-ca-the-ts-mirror-of-completeness-total-available-and-methodblock.md`,
`to: ia-cortex-60/lane/cortex-60` (scanner reads `addressee=cortex-60`). **Not committed by this lane** — it is in
cortex's tree. Carries field names, TS types and nullability for `EnumerateInstancesResponse` (`completeness` three-state,
non-nullable, default `"unknown"`; `total_available` `number|null`, null ≠ 0) and `MethodBlock`/`MethodInput` (JSON
produced by `model_dump`, not typed by hand), and `method?:` (omitted, not null) on the output envelope.

Findings in it that the architect should see:

* **cortex's `readMethod` differs from the SDK** on `value` (string vs scalar), `bound` (string vs number), three dropped
  fields (`unit`, `bound_defaulted`, `producer_sha` — cortex reported these), a `{name: value}` inputs map the SDK does
  not accept, and `inputs: []` (SDK-valid; cortex reads it as absent by a 2026-09-26 ruling). My reading, offered not
  imposed: the parity seal should assert the **wire** type; cortex's stringified display type is a separate projection.
* **The producer is looser-checked than the SDK model in one place.** `cost_agent/measures.py::_method` refuses
  `bound is None` xor `bound_defaulted is None`; `MethodBlock` does not. Not added — a ruling.
* **`completeness`/`total_available` exist only on the enumeration response**, not on the card envelope. Cortex's
  `CompetingMeasures` says its grandfathered `methods_compared`/`methods_answered` vocabulary stands "until
  `completeness`/`total_available` land"; the SDK defines no such field on that envelope. That sunset may be waiting on a
  field nobody has scheduled. Needs the architect.

### A CORRECTION to this lane's own 2026-09-25 handoff §1

That handoff (and the reconcile packet to 74) said a repo-wide search of `invincible-agent` found no
`MethodBlock`/`producer_sha`/`bound_defaulted`. **False for master as read now:** `producer_sha` and `bound_defaulted`
are in `agent_fleet/cost_agent/measures.py`, added `546e6bee` (2026-09-24) — *before* that search — and reconciled to the
list-of-`{name,value,unit?}` shape in `8b82761b` (2026-09-25 23:06). I did not establish which checkout the earlier search
ran in, so I cannot say why it missed them. The producer builds a plain dict and never imports `MethodBlock`, so
"nothing consumed the `list[str]` form" survives only in that narrow sense. The good news: the shapes agree by eye. The
bad: **no test ties producer to SDK model.** (This is the same-observation-opposite-reasons class — zero matches meant
"not searched where it lives", not "absent" — and the earlier search had no positive control.)

## 2. Identity proposal — DRAFTED, proposal only

`invincible-agent/sessions/2026-09-26-proposal-from-ca-an-initiator-kind-for-lane-sessions.md`, `to: the architect`
(addressee None by precedent). Not committed by this lane. Recommends `kind: "delegate"` with a required `on_behalf_of`,
refused wherever `service` is. Two findings it rests on, both read from source today:

* **The guard is a denylist copied in three places** — `interfaces.py:137`, fleet `mesh_graph.py:165`, `mesh_vectors.py:96`
  (`== "service"`). Widening the Literal alone would ADMIT a delegate everywhere. The guards must flip to `!= "person"`
  in the same change, and the seal should iterate the Literal's arguments so a fifth kind cannot slip past.
* **No code builds an `Initiator` from a token, and `CallerIdentity` has no kind.** "Kind is declared at the mint" is
  doctrine with no implementation; the only fleet `Initiator(...)` is a fixed `kind="service"` literal.

Five rulings owed are listed in §7 of the proposal; the real one is Model Y (delegate's own grants) vs Model X (RFC 8693
exchange; `sub` = operator, `act` = session). **Not verified:** whether the realm has token exchange enabled; whether
`/explain` filters per caller.

## 3. Standing

Code-tip diff (`711c6d0..lane/ca`, excluding `sessions/`): **still twelve files**, unchanged this order — nothing to add.
No shared store touched. `.claude/settings.local.json` still modified, still not this lane's.
Two packet files sit uncommitted in other trees (cortex-ui, invincible-agent), by rule.

Lane: ia-ca/lane/ca
