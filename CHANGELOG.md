# Changelog

All notable changes to `iagent_mesh` are recorded here, starting with this file's own
introduction at the 0.9.9 cut — earlier releases are not reconstructed retroactively; see `git
log` and `sessions/` for that history. Versions are `pyproject.toml`'s `version` field on
`master` at the tag named below, never a lane branch's own (lane branches do not bump their own
version field — it stays at the value it forked from until a release ceremony runs on `master`).

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
