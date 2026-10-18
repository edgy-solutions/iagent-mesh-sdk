# SDK adoption census — 2026-10-17

Read-only survey, no code changes. For every `invincible-agent` engine under `agent_fleet/` plus
the BFF (`cortex_bff/`, a thin shim over `src/iagent/gateway.py`): which `iagent_mesh` SDK
types/Protocols/functions it imports, and which local shapes still duplicate an SDK type instead
of importing it. This is the map for the next tagging decision — it makes no ruling of its own.

Checked against the SDK's current root `__all__` (`iagent_mesh/__init__.py`, 0.9.11) plus the
names deliberately kept module-qualified only (`discovery.resolve`, `task_kinds.{compose,
json_schema,validate_dir}`, `systems_of_record.{compose,validate_dir}`,
`registration_transport.{register_with_mesh,RegistrationResult}`,
`service_identity.{mint_token,mint_mesh_token,ServiceTokenError}`, `interfaces.*`,
`transport_auth.*`).

Built from five parallel read-only surveys (one per engine group below); methodology notes and
lower-confidence call-outs from each survey are folded into the findings section rather than the
table, to keep the table scannable.

## Table

| Engine | SDK root imports | SDK submodule-qualified imports | Local shapes duplicating an SDK type | Caveat |
|---|---|---|---|---|
| cortex_bff (the BFF) | `ContentKindRegistration`, `compose`, `load_task_kinds`, `SystemOfRecord`, `SystemOfRecordConnector`, `validate_connectors_known`, `match_system_of_record`, `Origin` | `interfaces.Initiator`, `interfaces.EdgeIdentity`, `interfaces.EdgeIdentityFilter`, `task_kinds.compose`, `systems_of_record.compose`, `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `Origin` (`src/iagent/origin.py:24`, fields `owner_domain,program,obtained_via`) ~ SDK `Origin` (`owner_domain,program,resolved_by,evidence`) — an older-vocabulary sibling coexisting in the same package with the real SDK `Origin` (imported elsewhere in the package as `_SorOrigin`) | Real BFF logic lives in `src/iagent/` outside `agent_fleet/`; `agent_fleet/cortex_bff/main.py` is a 17-line shim |
| mesh_registrar | `MeshWriteResult` | `interfaces.{EdgeIdentity,EdgeIdentityFilter,Initiator}`, `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `RegistrationManifest` (`main.py:122`) ~ `GraphManifest`+`SlotDecl` (near-total field match: name/input_uri/output_uri/owner_persona/domains/cost_class/requires_human_approval/timeout_s/synonyms/arity, plus a `slots` dict whose keys are exactly `SlotDecl`'s) | `RegistrationResult` (`main.py:381`) shares its name with SDK `registration_transport.RegistrationResult` but fields diverge enough to read as coincidental naming, not a true duplicate |
| graph_host | `GraphManifest`, `RefusalViolation`, `compose`, `enforce_refusal`, `registration_payload`, plus `fetch_row`/`row`/`holes_from`/`disposition_for`/`verdict_of`/`has_content`/`HOLE_DISPOSITIONS`/`NON_HOLE_DISPOSITIONS`/`ROW_DISPOSITIONS`/`VERDICT_KEYS` | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | One of the two heaviest direct root-import adopters surveyed (with cortex_bff) |
| ontology_service | `Initiator`, `MeshResult` | `interfaces.Initiator`, `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}`, `results.MeshResult` | `ResolveInstanceRequest` (`main.py:5007`) ~ SDK `ResolveInstanceRequest` (missing `user_email`/`entitled_domains`) | `instance_resolution.py`'s resolution dataclasses and `main.py`'s own provenance dict checked against `IdentityMatch`/`ConnectorLookup`/`ProvenanceBlock` — confirmed no close match, consistent with the 0.9.10/0.9.11 ruling that instance-resolution matching has no SDK model |
| safety_agent | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `ResolveRequest` (`main.py:516`, fields `identifier/query/class_uri`) ~ `ResolveInstanceRequest` — docstring literally calls it "the mesh's resolveInstance request" | Local `WorkOrder` (`entities.py:110`) shares a name with SDK `WorkOrder` but unrelated fields — name collision only, not structural |
| neo4j_expert | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `ResolveInstanceRequest` (`main.py:440`, `identifier/query` only) ~ SDK `ResolveInstanceRequest` | No test files found under this dir |
| data_analyst | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | No local `BaseModel`/dataclass/`TypedDict` classes exist in this service at all |
| finance_agent | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}`, `declarations.{DeclarationError,compose_rows}` | `ResolveRequest` (`main.py:662`, `identifier/query/class_uri`) ~ `ResolveInstanceRequest` — docstring explicitly notes the resemblance is intentional/known | `declarations.{DeclarationError,compose_rows}` imported via submodule path though both are root-listed SDK names — ambiguous bucket |
| planning_agent | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `ResolveInstanceRequest` (`main.py:540`) — **exact name collision** with the SDK's own root export, not imported; drops `user_email`/`entitled_domains`, the required-field validator, and `frozen`/`extra=forbid` | Materially looser reimplementation under the identical class name |
| restate_analyst | `CallerIdentity`, `compose_rows`, `read_rows` | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `workflow_definition.py` (no `iagent_mesh` import at all) reimplements the **entire** workflow/step family verbatim: `WorkflowDefinition`, `Step`, `HumanAwaitStep`, `SpoOperationStep`, `DirectCallStep`, `DispatchFanoutStep`, `RenderStep`, `SignalAwaitStep`, `WaitStep`, `EmitStep`, `CompletionPolicy`, `WorkflowDefinitionError`, `load_workflow_definition` — ~13 identically-named local models | The clearest "duplicates instead of adopts" case in the whole census — a full module, not a partial field subset. Lower-confidence, not flagged as duplicates: `workflow_join.py`'s `Approval`/`JoinStatus` vs. `ApprovalChainEntry`/`ApprovalOutcome`; `workflow_observation.py`'s `WorkflowRuntimeState` vs. `WorkflowCaseRecord`/`CaseTransition` |
| docs_agent | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | `reads.py`'s `PageRow`/`DocPageReader` loosely echo `MeshGraph`/`MeshOntology` shape but the file's own docstring calls this a deliberate placeholder — not asserted as a duplicate |
| presentation_agent | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | A comment names `enumeration.EnumerateInstancesResponse` as the shape a plain-dict envelope mirrors by key name only; no local class defined, so not counted |
| weaviate_expert | none | `interfaces.Initiator`, `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | Thin wrapper — zero local model classes; actual `MeshVectors`/`MeshVectorsWriter` plumbing lives in the shared `agent_fleet/utils/` layer (see below), outside this dir |
| datahub_wrapper | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | `ResolveInstanceRequest` (`main.py:506`, `identifier+query`) ~ SDK `ResolveInstanceRequest` — same name as the SDK Protocol model, hand-copied not aliased, missing `user_email`/`entitled_domains` | — |
| cost_agent | none | `transport_auth.{announce,current_caller,app_docs_kwargs,make_transport_auth_dependency}` | `ResolveRequest` (`main.py:442`, `identifier+query+class_uri`) ~ `ResolveInstanceRequest` — docstring self-admits "copied here field-for-field from the four providers that already work" | Self-documented duplication, not inferred |
| langgraph_support | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | Thin stub — single file, only transport_auth wiring |
| swarms_scraper | none | `transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` | none found | Thin stub — single file, no graph/vectors/ontology engine logic |

## Shared integration layer (`agent_fleet/utils/`, not an engine — context for the "none" rows above)

Several engines show no direct SDK import because the integration is centralized one level up,
in `agent_fleet/utils/`, and consumed from there:

- `mesh_registration.py` → `iagent_mesh.registration_transport.register_with_mesh`
- `service_identity.py` → `iagent_mesh.service_identity.{mint_token,mint_mesh_token,ServiceTokenError}`
- `mesh_vectors.py`, `mesh_writers/weaviate_vectors.py`, `mesh_writers/neo4j_graph.py` → the
  `MeshVectors`/`MeshVectorsWriter`/`MeshGraphWriter` Protocol implementations `weaviate_expert`
  and `neo4j_expert` run against
- `artifact_provenance.py` does **not** import `iagent_mesh` at all — its `DerivedProvenance`
  (`format_fingerprint`/`pipeline_version`/`version_missing`) is a different concept from
  `ProvenanceBlock` (trust-key derivation vs. ingest-time provenance), not a duplicate

## Cross-cutting findings

1. **`transport_auth.{announce,app_docs_kwargs,make_transport_auth_dependency}` is universal** —
   all 17 rows import it. It is the one SDK surface every engine has adopted without exception.
2. **`ResolveInstanceRequest` is reimplemented locally, un-imported, in 7 of 17 engines**:
   `ontology_service`, `safety_agent`, `neo4j_expert`, `datahub_wrapper`, `cost_agent`,
   `finance_agent`, `planning_agent`. Every copy is missing `user_email`/`entitled_domains` (the
   PR #38 caller-identity fields) relative to the SDK model. This is the single largest adoption
   gap the census found — the same wire shape, independently hand-copied seven times, three of
   them (`planning_agent`, `datahub_wrapper`, `ontology_service`'s is closest) under the SDK's
   own exact class name.
3. **`restate_analyst/workflow_definition.py` reimplements the entire workflow/step family**
   (`WorkflowDefinition` and all 8 step kinds) under identically-named local models with zero
   `iagent_mesh` import anywhere in the file — the clearest whole-module duplicate in the census,
   distinct from the partial-field `ResolveInstanceRequest` copies above.
4. **`mesh_registrar/main.py`'s `RegistrationManifest`** duplicates `GraphManifest`+`SlotDecl`
   field-for-field as a hand-rolled model.
5. **`cortex_bff`'s `src/iagent/origin.py`** carries a second, older-vocabulary `Origin`
   (`obtained_via`-keyed) alongside the real SDK `Origin` (`resolved_by`-keyed), which the same
   package already imports correctly elsewhere (`origin_writer.py`, aliased `_SorOrigin`) — a
   within-service split, not only a cross-service one.
6. **Six engines show no local duplicate at all**: `data_analyst`, `docs_agent`,
   `presentation_agent`, `langgraph_support`, `swarms_scraper`, `weaviate_expert`, `graph_host`.
   Several are thin stubs; `graph_host` and `data_analyst` are substantive services whose domain
   logic simply doesn't overlap any current SDK shape.
7. **Root-level adoption is concentrated in two engines** — `cortex_bff` and `graph_host` account
   for nearly all direct `from iagent_mesh import <Name>` usage found; every other engine reaches
   the SDK only through `transport_auth` and, for the `ResolveInstanceRequest` copies, not at all.
