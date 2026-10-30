# Changelog

All notable changes to `iagent_mesh` are recorded here, starting with this file's own
introduction at the 0.9.9 cut — earlier releases are not reconstructed retroactively; see `git
log` and `sessions/` for that history. Versions are `pyproject.toml`'s `version` field on
`master` at the tag named below, never a lane branch's own (lane branches do not bump their own
version field — it stays at the value it forked from until a release ceremony runs on `master`).

## 0.9.12 — 2026-10-30

### Added
- `WorkflowDefinition` step kinds gain an optional `stage: Optional[str] = None`, plus a
  definition-level validator; `EmitStep.disposes` — both from the architect's 2026-10-30
  "adoption program" directive.
- `normalize_mpn` (new `iagent_mesh/normalize.py` — no existing normalization module to extend).
  Generalizes doc-tools `notice_identity.py:138`'s `normalize_component`, the one correct
  producer; no ambiguity to resolve.
- `Refusal.to_terminal()` / `.from_terminal()` — specced by two already-written stopgaps on
  unmerged invincible-agent PR branches (`agent_fleet/utils/terminal_refusal.py`,
  `src/iagent/authz/refusal.py`), both naming this exact future SDK API: `"refusal:" +
  json.dumps({policy_id, missing_binding, grantable_by, candidates})`, a Restate `TerminalError`
  message payload. Resolves the open ruling-1 question from the 2026-10-25 policy-refusal-rule
  packet.
- The four ADR-0060 shapes as **types only** — `PersistenceDescriptor`/`PersistedClass`,
  `DocumentManifest`, `ArtifactRef`, `BlobRef` (new `iagent_mesh/persistence.py`) — inert,
  unwired, per ADR-0060 draft `11be1ec4` §5, which settles field shapes as this lane's to name
  while §6's behavioral items stay open for the architect.
- `ContentKindRegistration.persists: Optional[PersistenceDescriptor] = None`
  (`iagent_mesh/ingest.py`) — same "optional for every branch" precedent as `domain`/`label`/
  `review_shape`/`arrives_as`; no interaction with the existing `_branch_shape_is_consistent`
  validator.
- `vision_timeout` joins `REASON_CODES` (`iagent_mesh/ingest.py`), alongside new
  `RESERVED_TO_LANE_1`, `EMITTABLE_CODES` and `REASON_CODE_SLUG_RE` — a reason-code slug, not a
  duration constant (that's the pre-existing, explicitly distinct `timeout`, which stays in
  `RESERVED_TO_LANE_1` and out of `EMITTABLE_CODES`). Generalizes doc-tools 7f's
  `ingest_failure.py` `REASON_CODES` stopgap vocabulary.
- `ExportProfileHeader` (new `iagent_mesh/export_profile.py`) — `name`, `format` (open `str`),
  `granularity` (open `str`), `label`, `kinds`. Named by the architect as the SDK's one canonical
  header shape across three existing producers (PR #148; PR #144/#143; lane/01's PR #151/#158)
  that had disagreed on `scope` vs. `granularity` as the axis name — `granularity` wins here;
  `format`/`granularity` stay open strings rather than `Literal`s so naming the canonical shape
  doesn't also close off a future producer's value.
- `MeshGraph.is_safety_critical` (`iagent_mesh/interfaces.py`) — a bare, docstring-only Protocol
  method. **Type now, route later**: the one real decision-maker today is a static, domain-scoped
  list (`agent_fleet/safety_agent/safety_critical.py`, PR #125) whose own test bans a second
  implementation of this decision, so no implementation ships here. Waits on a concrete
  `MeshGraph` client (see "Not in this cut," below) and an explicit producer wiring.
- `ContentKindRegistration.review_shape` widens from `Optional[Literal["notice", "document"]]`
  to `Optional[str]` — **reopened 2026-10-30, reversing 2026-10-21's Q1 ruling on purpose**: a
  registry (`policy/review_shapes/<shape>.yaml`, platform seed + overlay) is now the
  deny-by-default boundary instead of a closed `Literal`, so this SDK's declaration no longer
  needs to enumerate every shape a future registry row might add. The realness-check moves from
  SDK declaration time to whichever layer serves the registry (BFF/leaf-picker).
- `ReviewCoverage`, `ReviewCoverageGroup`, `ReviewCoverageSharedFact`, `ReviewShapeRule`,
  `ReviewShapeRow` (new `iagent_mesh/review_coverage.py`) — typed from invincible-agent/lane/01's
  concrete 0.4.73 wire answer to cortex-ui's five blocking questions on the `parts`→`items`
  rename: `review_shape`/`item_kind` move to the top level (once per record, not per group);
  `groups`/`shared` carry open-`str` `rule` ids resolved against the same shape registry;
  `ReviewCoverageSharedFact.bbox` reuses `EvidenceRef.bbox`'s page-fraction, top-left-origin,
  `0..1` convention (ruled 2026-10-21) via an identical, non-`Optional` validator twin — pydantic
  validators can't be shared across two different `BaseModel` subclasses. `ReviewShapeRow` types
  the registry row itself (`review_shape`, `item_kind`, `rules_version`, `params`, `rules`).

### Not in this cut — spec only
- Concrete remote clients for `MeshGraph`/`MeshVectors`/`MeshOntology` over the invincible-agent
  gateway. Verified the gateway has no generic REST surface for any of the three protocols today
  (`grep -ncE "weaviate|SPARQL|sparql" invincible-agent/src/iagent/gateway.py` → `0`; a raw Neo4j
  driver and 14 bespoke Cypher call sites instead) — cross-repo infrastructure work, not an
  SDK-only task. Spec written and filed instead:
  `sessions/2026-10-30-spec-v0-9-13-concrete-remote-clients.md`. Deferred to 0.9.13.

## 0.9.11 — 2026-10-29

### Added
- `EvidenceRef` (`iagent_mesh/provenance.py`) / `ExtractionDefect.evidence_ref` — a structured
  sibling to `evidence`'s free-form strings: `page` (1-indexed) and `bbox` (`x0,y0,x1,y1`), for a
  source that has pages and coordinates to cite and a caller (e.g. a PDF viewer) that can jump
  straight to the region. `None` by default — `evidence` stays the required, always-present
  citation; this is the optional, additional, machine-locatable one. Tests only this cycle; no
  producer wires it yet.
  - **2026-10-21, `bbox`'s coordinate convention is now RULED, not open**: architect directive to
    doc-tools/7f, cortex-ui/master and this SDK together — `bbox` is a page fraction, `0..1`,
    origin TOP-LEFT (`(x0,y0)` upper-left, `(x1,y1)` lower-right, `y` increasing downward),
    unit-free by construction, the same everywhere `evidence_ref` appears, so no sibling `units`
    key ever rides beside it. `_bbox_is_well_formed` now rejects any coordinate outside `0..1` —
    a producer measuring in layout pixels or word-layer points (e.g. `gateway.py`'s own
    `_evidence_ref` dict, which carries `"units": "pt"|"px"` today) converts to this page-fraction
    space before constructing one. This replaces the original docstring's "points, pixels, or a
    normalized unit square are all legitimate" — that was never shipped to a producer, so nothing
    outside this SDK's own tests observed the prior, unconstrained shape.
  - **2026-10-21, `EvidenceRef.note`** (`Optional[str] = None`, must be non-blank when given) —
    item 4 of the same dry-run decision. invincible-agent/lane/01 found `evidence_ref` carrying
    two shapes under one name: a required free string on its BFF (row/header edits, e.g. `"page 1
    column header 'Customer Part Number'"`) vs. this SDK's `{page, bbox}` struct. The architect
    ruled this SDK's shape wins; the BFF's string becomes `note` here. The BFF (lane/01-202) runs
    its own mirror of this shape, accepting both the struct and the legacy string, until it
    imports this SDK at a version carrying `note`.
  - **2026-10-21, `bbox` is now `Optional[tuple[float, float, float, float]] = None`** (a second,
    later ruling the same day, superseding the line above that had `page`/`bbox` both staying
    required) — `page` may not be null, `bbox` may: a null `bbox` means "stated on this page, no
    box we can draw," for a citation the source only places on a page, not at a drawable region
    of it. A card rendering this jumps to the page with no outline and labels it "on page N, no
    box," rather than fabricating a box or refusing the citation. A derived field still carries no
    `evidence_ref` at all (ruled separately, unaffected) — null `bbox` is for a citation that IS
    page-located but has no finer locus, not for the absence of a citation.
- `ContentKindRegistration.id_namespaces` — generalizes invincible-agent/lane/74's PR #51
  (`register_engine_to_mesh(..., id_namespaces=[...])`, architect-ruled 2026-10-12) to this SDK's
  one registration surface: the ID prefixes a kind's own instances carry (e.g. `("HAZ-", "CSI-")`),
  validated the same way PR #51's registrar does (each entry at least 2 characters, no
  whitespace), plus the uniqueness check `passes`/`outputs` already enforce. Defaults to `()` —
  every kind before this field existed, and any kind whose identifiers carry no stable prefix.
  This module does not match or arbitrate on a contested prefix, same split `identity_field` and
  `parent_link_field` already draw: it declares the prefixes, not how a caller resolves them.
- `ContentKindRegistration.arrives_as` — architect's "leaf rule" ruling, 2026-10-21 (refines the
  Coordination note below): the arrival formats a kind's instances can come in as, e.g.
  `("pdf",)`, `("xml",)`, `("event",)`, a kind may name more than one. Defaults to `()` — every
  kind before this field existed, and an event kind that never arrives from a drop at all (e.g.
  `maintenance-fault-event`). Validated the same shape as `id_namespaces`/`passes`/`outputs`:
  each entry non-blank with no whitespace, no repeats. Combined with `domain`, this is the full
  leaf rule: "the leaves offered for a drop are the domain-declaring kinds whose `arrives_as`
  includes the drop's format" (e.g. a PDF drop offers every kind with `domain` set and `"pdf"`
  in `arrives_as` — `pcn`, `pdn`, `work-instruction`; not `s1000d`, which only arrives as `xml`).
  This module does not offer leaves or select from the registry — same split every field above
  already draws — ca adds the field, 7f fills in `KIND_MAPPING`'s rows with it, after the dry
  run (`pcn|pdn` stands as the literal list through Thursday's freeze).
  - **2026-10-21, invincible-agent/lane/01 asked three questions about this field; answered in a
    reply packet, no code change beyond what already shipped above**: (1) is `"cad"` allowed
    beside the ruling's three examples — yes, this is an open vocabulary, not a closed enum, same
    as `kind` itself; the validator only checks non-blank/no-whitespace. (2) should it be required
    for a domain-declaring kind — no, optional for every kind regardless of `domain`, same ruling
    `domain` itself drew in 0.9.7 ("an earlier draft... required it on every kind, which is
    exactly the hazard... identified"). (3) must a `branch="event"` row say exactly `("event",)` —
    no, this module infers nothing from `branch`, same split already drawn for `id_namespaces` on
    an event row.
  - **2026-10-22, architect confirmed directly, no divergence**: "`arrives_as`: tuple, empty by
    default (empty = offered for no format), and `cad` is a legal value" — matches what shipped
    above exactly. Also: "'Open vocabulary' is fine for now; if a typo'd format ever reaches the
    registry, we close it to an enum then" — a deliberate, acknowledged-provisional choice; the
    trigger for tightening it is a typo reaching the registry, not a design preference.
- `ContentKindRegistration.review_shape` — architect's "Q1" ruling, 2026-10-21, same leaf-rule
  cycle as `arrives_as`: `Literal["notice", "document"] | None`, naming which review card a
  promotion task opens for this kind's instances (`notice` for pcn/pdn's existing card,
  `document` for work-instruction and later kinds; the `document` reader itself is not yet
  built). `None` by default — every kind before this field existed, and any kind that never
  reaches a promotion task. invincible-agent/lane/01 left open whether a `branch="event"` row
  must leave it unset ("your call") — ruled optional for every branch, no exceptions, same
  precedent `domain` and `arrives_as` already drew: an unused declaration on an event row, not a
  forbidden one.
- `ContentKindRegistration.label` — architect ruling, 2026-10-21/22, closing a gap cortex-ui and
  doc-tools/7f both hit building against `arrives_as`: the registry had no human-readable name to
  serve alongside an offered leaf, so a reader fell back to upper-casing `kind` (correct for
  `PCN`, wrong for `work-instruction` → `WORK-INSTRUCTION`). `label: str | None = None` — this
  kind's own display name (e.g. `"Work Instruction"`). `None` by default; a caller with nothing
  to show falls back to `kind` itself, same as today. Optional for every kind, no exceptions, same
  "ruled optional, not required" precedent as `domain`/`arrives_as`/`review_shape` above — a
  display convenience, not a gate. This module does not render anything; it only declares the
  string.
- `STEWARD_ENTERED` (`"steward-entered"`) — the architect's ruling on 208's empty-notice task,
  2026-10-23, the seventh `obtained_via` rung and, per the ruling, the LAST one: a steward
  hand-entering a part no extraction ever produced, farther from truth than `steward-corrected`
  (which still has an extraction underneath it to correct). Appended to `OBTAINED_VIA` /
  `ObtainedVia` at the far end, exported next to `STEWARD_CORRECTED`. Rides through
  `make_provenance`/`ProvenanceBlock`'s existing constructor with no parallel path, per
  invincible-agent/lane/01's 2026-10-23 packet. Has its own paired-field rule — the architect's
  direct 2026-10-23 confirmation: `corrected_by` is REQUIRED (there was a steward, name them)
  and `extracted_value` is FORBIDDEN (there was no extraction for an entered row to differ
  from) — the mirror image of `steward-corrected`'s pairing, not the same one. Enforced on all
  three call sites (`ProvenanceBlock`'s validator, `make_provenance`, `validate_provenance`'s
  dict path). invincible-agent's own graph-write side (208) decides separately what else an
  entered row carries (`evidence_ref`, `extraction_defect`) — that is their shape to fill in,
  not this module's.
- `Refusal` (new module, `iagent_mesh/refusal.py`) — architect directive, 2026-10-24: a typed
  envelope for a denied authorization decision, for gov and fin to adopt. Four fields:
  `policy_id` (which policy refused), `missing_binding` (what grant was absent), `grantable_by`
  (who could grant it), `candidates: tuple[str, ...] = ()` (what else to try — may be empty, a
  dead end is itself informative, not an omission this field refuses). All four are opaque
  tokens — this module validates shape (non-blank, frozen, `extra="forbid"`) and nothing else;
  it does not decide, grant, or resolve anything, the same envelope/resolver split
  `ambiguous_in_class` (Coordination, below) predicted this ask would eventually take. Not wired
  into `MeshResult` — the directive asked for a standalone model, not a new outcome variant; a
  caller that wants one inside `MeshResult.failed(detail=...)` serializes it there itself.
  Exported at root (`from iagent_mesh import Refusal`), same pattern as `ExtractionDefect`.

### Coordination (no code change in this repo)
- **2026-10-21, "leaf types ... registry-driven, never a literal list"** (first of two architect
  directives on this; the second, above, adds `arrives_as`) — invincible-agent's `_review_leaf`
  hand-maintains `_LEAVES = ("pcn", "pdn")`; the ruling asks it to read the allowed leaves from
  the content-kind registry's "domain-declaring kinds" instead, after the dry run (`pcn|pdn`
  stands as-is through Thursday's freeze). This SDK already ships the surface that makes that
  possible: `ContentKindRegistration.domain` (0.9.7) is exactly "the kind's HOME audience" —
  filtering registry rows on `domain is not None` IS "domain-declaring kinds, read from the
  registry." No new field, no change here: this module ships no rows to filter (`docs/outbound`
  disclaimer on `ContentKindRegistration`: "THIS SDK DOES NOT SHIP ANY ROWS... lives in
  doc-tools, not here") — the registry-driven read is doc-tools'/invincible-agent's own code to
  write, against a field this SDK already has.
- `ingest_id`/`notice_id` on "the task payload type" — paused, not enough spec. No generic
  task-payload envelope model exists in this SDK; `TaskKind` (`task_kinds.py`) is a
  vocabulary/declaration row whose own docstring mandates "generic at birth... nothing may name
  a domain," so the fields don't belong there. `ingest_id`/`notice_id` together exist only in
  invincible-agent's own consumer code (`gateway.py`, `decision_record.py`); no packet in either
  repo originates this ask or names what a new envelope model needs beyond these two fields.
  Needs a packet before this repo designs a new model from nothing.
- `ambiguous_in_class` ("refusal shape" ask) — investigated and does not apply here, same shape
  of ruling as `safety:onPlatform` in 0.9.10: how a deployment resolves instances is its own
  business, this SDK models the envelope, not the resolver. `ambiguous_in_domain`, its only
  existing sibling, is purely free-text today — a value of an ad-hoc `instance_match` string
  field in invincible-agent's own provenance dict (`agent_fleet/ontology_service/main.py`), never
  touching any SDK model — and 0.9.10 already ruled that instance-resolution matching admits no
  SDK Protocol or response model at all. `ambiguous_in_class` itself isn't even packeted to this
  repo yet: it's a 2026-10-15 pre-packet from invincible-agent/lane/saf to lane/74 about a
  same-class score tie in `decide()` (`instance_resolution.py`), framed as a test fixture, not a
  proposal here. Nothing to do in this repo for `decide()` itself. **2026-10-24 — the predicted
  envelope field arrived, as a direct ruling rather than a packet**: see the `Refusal` entry
  above. `decide()`'s own matching logic is unaffected; only the envelope moved.
- `extraction_defect` producer/SDK-model mismatch (rev 188, invincible-agent/lane/01) — the
  architect's ruling stands from 0.9.10: Lane 1 aligns `defect_task()`'s payload to this SDK's
  `ExtractionDefect`, this SDK does not widen to the decision-shaped payload Lane 1 recommended in
  their 2026-10-12 contract-fork packet. Recorded here because that packet explicitly asked for
  the widening and this cycle's instruction confirms the ruling held, not because anything changed.
- `header_edits` and `leaf`/`leaf_source` ("the review types" ask, 2026-10-20) — ruled out, same
  shape as `ambiguous_in_class` above: `HumanTaskActRequest`, `header_edits`' decision-gating
  (`promoted`-only, one entry per field) and `leaf`/`leaf_source`'s `_review_leaf` heuristic are
  invincible-agent's own review-task HTTP API (`gateway.py`), not mesh substrate vocabulary — this
  SDK models the envelope, not the resolver, the same line 0.9.10/0.9.11 already drew for
  instance-resolution matching. `HeaderEdit.field` (`mfr`/`notice_id`/`notice_date`) and `leaf`
  (`pcn`/`pdn`) are concrete domain vocabulary besides: generalizing them into this SDK would mean
  inventing a "review types" family from nothing to host values the SDK's own `generic at birth`
  discipline refuses to carry. The provenance is also weaker than every prior drop this cycle: the
  source, invincible-agent's `lane/01-197`, is not yet on that repo's `master`. The SDK's own
  responsibility in this area already ends at `ExtractionDefect`/`EvidenceRef` (this cycle's first
  drop) — each `header_edits`/`row_edits` correction files one of those, independent of the wire
  shape that carries it to the server. Nothing to do in this repo.
- `steward-entered` and `corrected_by` — RESOLVED, moved out of Coordination: this was an open
  question in ca's first reply (the four explicit asks didn't touch the pairing validator, but
  the ruling's own prose implied `corrected_by` should ride). The architect's direct 2026-10-23
  follow-up confirmed reading (b) — `corrected_by` required, `extracted_value` forbidden under
  `steward-entered` — and that is now code, not a flag; see the `STEWARD_ENTERED` entry above.
- `document` in the content-kind vocabulary and `review_shape` enum (2026-10-24 directive) —
  **already shipped, no code change**: `CONTENT_KIND_BRANCHES = ("document", "event")`
  (`ingest.py:136`, `"document"` is even `ContentKindRegistration.branch`'s default) since the
  content-kind-branch work, and `review_shape: Literal["notice", "document"] | None` since
  `149e491` (2026-10-22, the leaf-rule cycle above). Flagging rather than silently treating as
  done, in case the directive meant a third place this repo hasn't found — nothing else in this
  module names a closed `document`/`notice`-shaped vocabulary that's missing the value.

## 0.9.10 — 2026-10-12

**Tag re-pointed.** `v0.9.10` was first cut directly at `lane/ca-0.9.10`'s tip (`c85258f`),
per this cycle's "no tag until Lane 1 asks" governing instruction — but `pyproject.toml` stays
pinned to its fork value on a lane branch by this file's own rule above, so that tag pointed at
a commit still reporting `0.9.9`. invincible-agent/lane/01's rev-188 packet (filed in
`sessions/2026-10-11-packet-to-ca-tag-0-9-10-for-rev-188.md`) named the real consequence: rev
188 pins the SDK by importing it and reading its version string, so a tag whose package still
says `0.9.9` doesn't pin what its name claims. Ran the release ceremony properly instead: folded
`lane/ca-0.9.10` into `master`, bumped `pyproject.toml` here, and moved the `v0.9.10` tag off
`c85258f` onto this cut's own version-bump commit. The two lane commits this brings in
(`b1b7f96`, `c85258f`) are unchanged by the re-point.

### Added
- `Initiator.authz_id` — a second opaque identity claim, for deployments whose authorization
  decider keys on a different claim than `subject` (e.g. invincible-agent's `GatewayArtifacts`:
  owner check on `subject`, delegate map on `authz_id`). Unconstrained by `kind`, unlike
  `on_behalf_of` — no proposal yet says which kinds require or forbid it.
- `check_mesh_artifacts_list_by_kind_contract` — the list-route sibling of
  `check_mesh_artifacts_entitlement_contract`: proves `list_by_kind` scopes by entitlement
  (entitled→rows, entitled-to-none→empty, absent kind→empty) without asserting anything about a
  partially-entitled caller's row count, which the Protocol's own docstring rules is a correctly
  scoped list's intended shape, not a gap.
- `check_system_of_record_query_independence_contract` — proves one `SystemOfRecordQuery`
  connector instance answers two different values independently: querying B must not perturb a
  later re-query of A, and each result stays its own re-iterable collection. `query()` takes no
  `Initiator`, so this is not an entitlement arm — per-caller scoping for this Protocol is the
  caller's own concern (confirmed against lane/saf's FRACAS consumer).

- `OBTAINED_VIA.STEWARD_CORRECTED` (`"steward-corrected"`) — a sixth rung, appended at the same
  far end as `user-drop`: a steward retyping a value automated extraction got wrong is a human
  intermediary correcting a reading, not the authoritative system itself, the same kind of hop
  `manual-export`/`user-drop` already are. Ruled by invincible-agent/lane/01's steward-correction
  packet (2026-10-10), which superseded its own same-night draft asking for a terminal-reject
  retry path instead.
- `ProvenanceBlock.corrected_by` / `ProvenanceBlock.extracted_value` — ride together, and only
  under `obtained_via='steward-corrected'`: who corrected the claim, and what automated
  extraction produced before the correction (the corrected value is just the field's own current
  content, never duplicated). Enforced on both entry points (`make_provenance`,
  `ProvenanceBlock`) and the dict re-check path (`validate_provenance`).
- `ExtractionDefect` — the admin-queue record the same ruling names, filed once per correction
  independent of what rides in the graph row's own `ProvenanceBlock`: `artifact_id`, `pin_digest`,
  `extracted_value`, `corrected_value`, `evidence` (non-empty, same grammar as `Origin.evidence`).
  Generalizes the ruling's own domain field names (`notice`, `extracted`, `corrected`) to this
  SDK's generic vocabulary — no `notice`, no PCN, anywhere in this surface. No `corrected_by`
  here: the review-resolve task that mints one already carries its actor.
- `check_provenance_floor_contract` / `check_provenance_sources_contract` needed no change for
  this growth — both reason over `OBTAINED_VIA` by name (`DIRECT`, `USER_DROP`), not by
  exhaustive position or count.
- `ResolveInstanceRequest` — the wire shape of a `mesh:resolveInstance` provider call:
  `identifier` (required), `query`, `user_email`, `entitled_domains`. Generalizes
  invincible-agent/lane/74's PR #38 (commit `251f4097`, 2026-10-10), which settled these exact
  field names across every call site after gov's origin-at-read report: a provider holding
  origin-scoped instances cannot gate on a caller it was never told. This model carries the wire
  shape only — it does not gate; empty `user_email`/`entitled_domains` is how "no caller" is
  represented, not a validation failure.

### Coordination (no code change in this repo)
- Packet to `invincible-agent/lane/01` naming `frontend_version` as the field `InterviewRequest`
  needs to declare to unblock cortex-ui's `feat/frontend-version-on-ask` worktree — that model is
  owned by `invincible-agent/src/iagent/gateway.py`, not this SDK; nothing here to change.
- `safety:onPlatform` ("ontology bundle" ask) — investigated and does not apply here: this SDK
  has no ontology-bundle concept at all (`schemas/` holds one unrelated JSON schema; nothing else
  ships or bundles an ontology). The property belongs to invincible-agent's own
  `safety_extension.ttl`, and the hazard-shape work that would have declared it was PARKED by an
  architect ruling the same day (2026-10-10) — only the name (`platform`, not `program`) survived.
  Nothing to do in this repo.
- `user_email`/`entitled_domains` on `ResolveInstanceRequest` — PR #38 (above) already closes the
  gap on the invincible-agent side with these exact field names; no residual to packet back to
  lane/74.

## 0.9.9 — 2026-10-09

First tagged cut since v0.9.8; v0.9.7 was requested but never actually tagged, so several items
below reached a tagged `master` for the first time here even though they landed on a lane branch
earlier.

### Added
- `check_ontology_writer_graph_isolation_contract` — the `MeshOntologyWriter` conformance suite's
  second isolation arm: an upsert into graph A must be invisible from a DIFFERENT NAMED graph B,
  not only from Jena's default graph (`check_ontology_writer_contract`'s existing arm).
- `SystemOfRecordQuery` — a many-record sibling to `SystemOfRecordConnector.lookup`, plus
  `check_system_of_record_query_contract` admitting it (lane/saf's proposal 1, ADR-0056).
- `WorkflowDefinition` — the ADR-0029 process schema ADR-0039 extends, validated against the 8
  step kinds.
- `WorkflowCaseRecord` — the ADR-0039 case-runner record (`CaseState` stays off the wire).
- `MeshArtifacts` — a new read-only Protocol for named reads over the artifact store, plus
  `check_mesh_artifacts_entitlement_contract`.
- `MeshVectorsWriter.has()`.
- `ContentKindRegistration.parent_link_field`.
- `check_provenance_floor_contract` / `check_provenance_sources_contract` — generic contracts
  stating the invariants this SDK's own `OBTAINED_VIA` ordering and `promoted` ingest stage force
  on a caller-side "weakest provenance behind an answer" or "per-source provenance list" function;
  neither contract admits an SDK Protocol implementation (there isn't one), both exist so a fleet
  lane can run its own such function against this SDK's vocabulary without this SDK importing or
  knowing about it.

### Changed
- `MeshArtifacts.kind` is now documented as opaque to the Protocol, not required to be
  `ContentKindRegistration.kind`'s vocabulary — `ContentKindRegistration` rows are one valid
  source among possibly others; a deployment may declare its own stable kind strings (e.g.
  `"answer-artifact"`) for fleet-produced artifacts without a second registry construct. Ruled
  against the fleet's first real `MeshArtifacts` consumer, which reads a produced answer artifact
  that no `ContentKindRegistration` row could honestly express. No runtime change — the prior
  text was already unenforced, so this corrects the docstring to match what already type-checked.

### Carried forward (first reaching a tagged master at this cut)
- `MeshGraphWriter.write_node` (opened v0.9.6 scope) and `has_node`/`delete_node` (opened v0.9.7
  scope, never itself tagged), each with their own conformance arm.
- `SystemOfRecord`/`Origin` models.
- `maintenance_bridge` — `ActionRecord`/`MaintenanceEvent`/`ApprovalChainEntry`.
