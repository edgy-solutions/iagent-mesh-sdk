# Changelog

All notable changes to `iagent_mesh` are recorded here, starting with this file's own
introduction at the 0.9.9 cut — earlier releases are not reconstructed retroactively; see `git
log` and `sessions/` for that history. Versions are `pyproject.toml`'s `version` field on
`master` at the tag named below, never a lane branch's own (lane branches do not bump their own
version field — it stays at the value it forked from until a release ceremony runs on `master`).

## Unreleased — `lane/ca-0.9.10`

On a lane branch, not tagged — per this cycle's own governing instruction, no tag until Lane 1
asks. `pyproject.toml`'s `version` is unchanged at `0.9.9` on this branch; it only moves at the
next release ceremony on `master`.

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

### Coordination (no code change in this repo)
- Packet to `invincible-agent/lane/01` naming `frontend_version` as the field `InterviewRequest`
  needs to declare to unblock cortex-ui's `feat/frontend-version-on-ask` worktree — that model is
  owned by `invincible-agent/src/iagent/gateway.py`, not this SDK; nothing here to change.

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
