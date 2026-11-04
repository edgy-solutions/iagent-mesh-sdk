# Adoption ratchet report — what `invincible-agent` still copies instead of importing

**From:** iagent-mesh-sdk/lane/ca-0.9.13
**Date:** 2026-11-03
**Scope:** directive part (c) of "ca: MeshData handle spec → Protocol + doc in SDK; v0.9.14 draft
notes; adoption ratchet report (what BFF still copies instead of importing)." Parts (a) and (b)
shipped as commits `2b699af` and `41a7b92`.

**Method:** `iagent_mesh.sdk_adoption.find_hand_copied_types(package_root)` — AST-parses a
third-party package root (never imports/execs) and flags a top-level `class Foo:` statement whose
name matches an `iagent_mesh.__all__` export and is not that export's own canonical source file.
Run directly against `invincible-agent` this session (not relayed from a subagent). Every finding
below was independently re-read in source after the scanner flagged it; two were ruled OUT because
direct reading showed the scanner's syntactic match doesn't mean "duplicate" (see Excluded,
below).

---

## 1. The big one: `agent_fleet/restate_analyst/workflow_definition.py`

The scanner flags **11 classes** in this one file, all SDK-exported names, all top-level `class`
statements, none the SDK's own canonical definition:

```
WorkflowDefinitionError, CompletionPolicy, HumanAwaitStep, SpoOperationStep, DirectCallStep,
DispatchFanoutStep, RenderStep, SignalAwaitStep, WaitStep, EmitStep, WorkflowDefinition
```

This isn't one hand-copied type — it's substantially the entire SDK `workflow_definition.py`
module, reimplemented under restate_analyst's own fleet engine. Spot-checked `EmitStep`: both
sides declare `disposes: Optional[str]` with the identical `pattern=r"^[a-z][a-z0-9_]*$"`
(`iagent_mesh/workflow_definition.py:281` vs. the local file's line 394) — not a coincidental name
collision, the same field, same constraint, copied.

**Disposition:** the largest adoption gap in the fleet by class count, and the only one this
report found outside the BFF proper. Unknown whether this predates the SDK's own
`workflow_definition.py` existing as an importable module, or is a parallel fork that drifted.
Worth its own lane packet to restate_analyst, separate from this report — not filed here, since it
names a different owning lane than the BFF findings below and deserves its own investigation of
*why* (predates import availability? needs a restate-specific subclass the SDK doesn't support?)
before proposing convergence.

---

## 2. The BFF (`src/iagent/`) — four scanner hits, two already resolved differently

### 2a. `gateway.py:1384` `ReviewCoverage` — EXCLUDED, not a gap

Already ruled by lane/01's own 2026-10-30 "three forks" packet (Fork 3): a deliberately-kept
deprecated `parts`-form compatibility shim, scheduled for deletion in 0.4.74, blocked on
cortex-ui's own migration (`src/lib/reviewCoverage.ts`, still on the old form as of lane/01's
2026-10-31 follow-up). The scanner's syntactic match is correct; it is not a hand-copy needing
conversion. Listed here only so this report doesn't look like it missed it.

### 2b. `ingest_api.py:106` `ArtifactRef` — open, not yet actionable

A more detailed local shape than the SDK's own minimal, `id`-only `ArtifactRef`
(`iagent_mesh/persistence.py:75-90`), whose own docstring flags it as still-open pending an
architect ruling on whether it becomes `MeshArtifacts.get`'s payload. Not confirmed as "the same
concept, hand-copied" — it may be a genuinely different, wider shape this repo needs regardless of
what the SDK's `ArtifactRef` settles into. No recommendation beyond: re-examine once the SDK-side
ruling lands.

### 2c. `ingest_api.py:200` `EvidenceRef` — ACTIONABLE: the stated blocker appears cleared

Lane/01's 2026-10-31 packet named this exact, specific ask as the precondition for swapping to an
SDK import:

> "`note` stays optional but omits null from its schema (e.g. `SkipJsonSchema[None]`, or a default
> with no null arm). `bbox` renders as an array of exactly 4 numbers, each 0..1. Validation is
> unchanged. Then I swap the import in 0.4.74 or 0.4.75."

Verified this session by rendering `EvidenceRef.model_json_schema()` directly against the live
SDK code (`iagent_mesh/provenance.py:329-400`):

- `note` — optional, schema omits `null` (no `anyOf` with `{"type": "null"}`).
- `bbox` — `prefixItems` of exactly 4 items, each `{"minimum": 0.0, "maximum": 1.0}`.

Both asks are satisfied. The gateway half of this fork already converged independently (confirmed
by reading `gateway.py:1255-1295`: `_wire_evidence_ref` now calls `EvidenceRef.model_validate(v)`
against the SDK model, with an inline comment "Architect ruling 2026-10-31: the SDK's rule wins").
Only `ingest_api.py:200` remains.

**Not independently re-run this session:** `invincible-agent/tests/
test_an_evidence_ref_is_the_sdks_rule_page_fractions_or_a_422.py` (the equivalence seal lane/01
built to hold both models to the same accept/refuse verdict in the meantime) — confirmed it has
no skip/xfail markers, but it hasn't been executed this session (would need invincible-agent's own
venv). Recommend lane/01 re-run that seal before the import swap, not take this report's schema
render as a substitute for it.

### 2d. `provenance.py:62` `ProvenanceIncomplete` — the plain one

Near-verbatim duplicate of `iagent_mesh.provenance.ProvenanceIncomplete` / `make_provenance`
(`_REQUIRED` tuple and all), with no comment anywhere in the local file acknowledging the SDK has
this already. No stated blocker, no version pin, no "waiting on X" — unlike `EvidenceRef`'s
documented convergence plan, this one reads as an unflagged oversight rather than a deliberate
holdout.

---

## 3. One the AST scanner structurally cannot see

`src/iagent/authz/refusal.py:124`, function `refusal(policy_id, missing_binding, candidates=())`,
returns a plain `dict` — not a `class` statement, so `find_hand_copied_types` (which only matches
`class Foo:`) cannot flag it. Reading the module directly:

- Its own docstring names the SDK type it mirrors explicitly: *"Every policy refusal carries a
  `refusal` object in the SDK's envelope shape (`iagent_mesh.refusal.Refusal`, SDK 0.9.11, commit
  `26b1238`; this repo pins 0.9.10, so the body is built as a dict with exactly the model's fields
  and validates against it unchanged on the bump)."*
- `FIELDS = ("policy_id", "missing_binding", "grantable_by", "candidates")` — declared explicitly
  to track `Refusal`'s own field order.
- The `refusal()` function's return dict matches those four keys exactly.

**ACTIONABLE, same shape as 2c:** the stated convergence condition — "this repo pins 0.9.10...
unchanged on the bump" — has already been met. `invincible-agent/pyproject.toml:66,146` now pins
`iagent-mesh-sdk.git@v0.9.12`, two versions past the 0.9.10 the docstring names, and past 0.9.11
where `Refusal` itself landed. The file still hand-builds the dict instead of importing `Refusal`.
This is the second concrete, stated-blocker-now-cleared finding, independent of `EvidenceRef`.

(`PartialRefusal` — built for the `grantable_by`-unknown-at-construction-time case — shipped in
`5c815b2`, tagged into `v0.9.13`, which invincible-agent does not yet pin; that one genuinely isn't
available yet. The plain `Refusal` import is what's cleared, not `PartialRefusal`.)

---

## 4. Deliberate non-adoption — not a gap

`agent_fleet/utils/terminal_refusal.py` — stdlib-only, no `iagent_mesh` import, by design: it sits
on the deny path and avoiding any import risk there is the point (per
`project_partial_refusal_added` memory — `PartialRefusal` was built specifically to let this module
eventually converge, but porting it is invincible-agent's own task on its own schedule, not a gap
this report is flagging).

---

## Summary table

| Finding | Location | Status |
|---|---|---|
| Entire workflow DSL hand-copied (11 classes) | `agent_fleet/restate_analyst/workflow_definition.py` | Open — needs its own investigation, separate packet |
| `ReviewCoverage` | `gateway.py:1384` | Excluded — ruled non-duplicate, scheduled deletion |
| `ArtifactRef` | `ingest_api.py:106` | Open — pending SDK-side scope ruling |
| `EvidenceRef` | `ingest_api.py:200` | **Actionable — stated blocker verified cleared** |
| `ProvenanceIncomplete` | `provenance.py:62` | Open — unflagged plain duplicate |
| `refusal()` dict shape | `authz/refusal.py:124` | **Actionable — stated version-pin blocker verified cleared** |
| `terminal_refusal.py` | `agent_fleet/utils/` | Not a gap — deliberate, by design |

Two items (`EvidenceRef`, `refusal()`) are ready for lane/01 to act on now: both named their own
convergence condition in writing, and both conditions are met in the live SDK/live pin. Worth a
short follow-up packet to lane/01 confirming this, separate from the full report.
