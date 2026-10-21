# Changelog

All notable changes to `iagent_mesh` are recorded here, starting with this file's own
introduction at the 0.9.9 cut — earlier releases are not reconstructed retroactively; see `git
log` and `sessions/` for that history. Versions are `pyproject.toml`'s `version` field on
`master` at the tag named below, never a lane branch's own (lane branches do not bump their own
version field — it stays at the value it forked from until a release ceremony runs on `master`).

## Unreleased — `lane/ca-0.9.11`

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

### Coordination (no code change in this repo)
- **2026-10-21, "leaf types ... registry-driven, never a literal list"** (architect directive,
  item 2, same packet as the `bbox`-Optional ruling above) — invincible-agent's `_review_leaf`
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
  proposal here. Nothing to do in this repo. If lane/74's `decide()` later needs a refusal
  *envelope* field a caller (e.g. cortex-ui) draws on generically for elicitation — a candidates
  list, not the matching logic itself — that comes to `ca` as its own packet and gets ruled then.
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
