to: Chris
from: iagent-mesh-sdk/lane/ca
date: 2026-10-29
re: status report — measured this session, not recalled from memory

# 1. v0.9.11 tag + adoption PRs

**Tag:** cut today. Confirmed by fresh `git tag`/`git log`, not by a sessions-file claim — a
prior packet asserted "Tag v0.9.11" on 2026-10-28, but no such tag existed until this session cut
it. Lane 1 confirmed 207's sha (`a31b61cb`, invincible-agent master) on 2026-10-26 and
re-verified 2026-10-28; the gap between confirmation and cut was ca's, not a missing input.
Ceremony: merged `lane/ca-0.9.11` → `master` (`1ab1796`), bumped `pyproject.toml`/`uv.lock`
(`2a0f951`), full suite re-verified post-fold (897 passed, 2 skipped), tagged `v0.9.11` at
`2a0f951`, pushed. Ships: `id_namespaces`, `EvidenceRef`/`evidence_ref`, `arrives_as`,
`review_shape`, `label`, `STEWARD_ENTERED` (7th/last `obtained_via` rung), `Refusal`.

**Adoption PRs, per repo (grepped, not inferred):**
| Repo | PR | Status |
|---|---|---|
| invincible-agent | #83 | Merged. `ResolveInstanceRequest` imported in 3 of 7 census-named engines. |
| cortex-ui | none | No Python/`iagent_mesh` dependency exists — pure TS/Vite, pulls `@platform/iagent-contracts` from invincible-agent#master instead. "Pinned to v0.9.8" doesn't apply here. |
| doc-tools | none | Pinned to v0.9.8 (`requires.txt`). Zero adoption of any of the 8 surfaces below — its only `iagent_mesh` import anywhere is `mint_token`. |

# 2. v0.9.12

**Does not exist** — no tag, branch, CHANGELOG entry, or sessions/ mention anywhere. Current
version is 0.9.11, cut today. Two drift packets have landed naming candidate scope, neither
started:
- `stage: Optional[str]` + a validator on workflow steps (packet 2026-10-30, invincible-agent #155).
- `disposes: Optional[str]` on `EmitStep` (packet 2026-10-30, invincible-agent #157).

A third input bears on scope, not code: the architect has directed the BFF to import
`EvidenceRef`/`Refusal` now (both already in v0.9.11) and `kinds`/`review_shape`/`provenance`
types once v0.9.12 lands. Per the table below, the SDK already carries all three in full
(`ContentKindRegistration.{id_namespaces,arrives_as,review_shape,label}`;
`ProvenanceBlock`/`EvidenceRef`/`ExtractionDefect`/`STEWARD_ENTERED`) — so that part of v0.9.12
may need no new types, only the two field drifts above. Lane 1 is waiting on this answer; not yet
sent back.

# 3. SDK surfaces — exists, who's on the SDK path, what ADR-0060 still needs

| Surface | In SDK? | Fleet adoption (SDK-path vs direct/local-mirror; 18 engines) | ADR-0060 gap |
|---|---|---|---|
| vector (Weaviate) | Yes — `MeshVectors` protocol, no concrete remote client | weaviate_expert splits 4/4 via a runtime toggle; mesh_registrar, neo4j_expert direct-only; ontology_service splits 3/3; 13 others 0/0 | No `PersistenceDescriptor`/`ArtifactRef`/`visible_by_origin` anywhere; `nominate()` has no origin filter |
| graph (Neo4j) | Yes — `MeshGraph` protocol, same caveat | neo4j_expert (the SDK's own candidate implementer) is 0/2 — direct-only; ontology_service splits 11/3; others 0/0 | same gap |
| ontology (Jena/TTL) | Yes — `MeshOntology`, sibling class to `MeshGraph` | ontology_service (the SDK's implementer) splits 18/38 and still falls back to local rdflib; docs_agent reads ontology via raw HTTP — no SDK client exists for it to use | same gap |
| network/transport | Yes, but no single protocol — `MeshClient`, `transport_auth`, `service_identity`, `delegate_identity`, `registration_transport` | near-universal: ~1 call per engine (mounting the auth dependency once); heavier "direct" counts are mostly external tools (Dagster/Superset), not engine-to-engine | not what ADR-0060 gates |
| provenance | Yes — `ProvenanceBlock`/`EvidenceRef`/`ExtractionDefect`/`STEWARD_ENTERED` | restate_analyst: 1 real SDK call site, plus 3 files with local dict-key mirrors of `obtained_via`; ontology_service: 0 SDK use, a parallel local pydantic shape instead; 16 others 0/0 | draft doesn't reference these types at all outside generic prose |
| kinds (`ContentKindRegistration`) | Yes — `id_namespaces`/`arrives_as`/`review_shape`/`label` all shipped | 0/18 — zero imports or constructions anywhere | ADR-0060 explicitly calls for a new `persists` field here — not built |
| refusal (`Refusal`) | Yes — `policy_id`/`missing_binding`/`grantable_by`/`candidates` | 0/18 — confirmed via 4 separate greps, all empty | draft doesn't reference `Refusal` at all — orthogonal, not yet wired |
| export | **No export-out surface exists.** Closest is `MeshWriteResult` (`write_results.py`), explicitly a write-IN type, not export-out | `MeshWriteResult`: mesh_registrar 2 uses, shared (non-engine) `utils/mesh_writers/` 19+22 uses, 17 other engines 0/0 | draft calls for `DocumentManifest`/`ArtifactRef`/`BlobRef` — zero hits anywhere, proposed-not-built |

# 4. ADR-0060 — net

The draft itself lives only on `lane/01-adr-0060` (commit `11be1ec4`), not merged to any master.
Of the four new shapes it proposes (`persists` field, `PersistenceDescriptor`, `DocumentManifest`,
`ArtifactRef`/`BlobRef`), none exist in the SDK or anywhere in the fleet. Of the 8 surfaces above,
only provenance has even one real fleet-side SDK consumer today (restate_analyst, one call site);
kinds and refusal have none. "Through the mesh" is a real SDK capability for 3 of 8 surfaces
(vector/graph/ontology) via protocols with no shipped concrete client, and a design-only proposal
for the rest.
