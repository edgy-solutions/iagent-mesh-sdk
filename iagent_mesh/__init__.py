# iagent_mesh namespace
from .client import MeshClient, MeshResponse
from .shapes import (
    ARCHETYPE_BAML_NAME,
    VERB_OUTPUT_URI,
    Archetypes,
    InputShapes,
    OutputShapes,
)

# Identity is part of the SDK's public surface, not an internal of transport_auth: a tool
# handler annotates a parameter `CallerIdentity` and a helper below it calls `current_caller()`.
# Importing those from a module named `transport_auth` misfiles them as a transport concern —
# they are the answer to "who is asking", which is the whole per-user read path.
#
# ── EAGER, AND THAT IS NOW CORRECT — THE FIX LIVES IN `transport_auth`, NOT HERE ─────────
# This line once made `import iagent_mesh` require a web framework, because `transport_auth`
# imported fastapi unguarded. It was briefly made lazy (PEP 562 `__getattr__`) to dodge that.
# THAT FIX WAS WRONG, and the reason is worth keeping so nobody re-applies it:
#
# `current_caller` is EXPORTED FROM the fastapi-importing module. Deferring the import does not
# remove the dependency — it moves the failure from `import iagent_mesh` to the first CALL of
# the very function a non-web consumer installed the SDK for. Same outcome, later, and harder
# to diagnose. dag-tools soft-imports this name inside a bare `except`, so under the lazy shape
# the import SUCCEEDS and the call fails somewhere with no handler expecting it.
#
# The real split is inside `transport_auth`: `CallerIdentity` and `current_caller` touch no
# fastapi symbol at all — only the server dependency factory does. Guarding the import THERE
# gives the client surface a framework-free path, so this import is once again free, and the
# `[server]` extra means what an extra should mean: you lose the SERVER helpers, not the
# ability to import.
from .transport_auth import CallerIdentity, current_caller


# A graph's CONTRACT and the helper that makes it a verb. Public surface, not an internal of a
# host engine: a team running their own host (ADR-0046 §8.5 route C) imports exactly these, so
# "plug into our host" vs "run your own" is a deployment choice rather than a second
# implementation. The same `validate_dir` is what the policy repo's PR gate imports and what
# the seed cronjob runs against the composed result — one validator, two rails.
from .graph_manifest import (
    REFUSAL_DISPOSITIONS,
    REF_COSMETIC,
    SLOT_KINDS,
    GraphManifest,
    ManifestError,
    RefusalViolation,
    SlotDecl,
    compose,
    enforce_refusal,
    json_schema,
    load_manifests,
    manifest_ref,
    ref_basis,
    register_graph,
    registration_payload,
    validate_dir,
)

# ── THE INTERFACE SURFACE: reachable from `import iagent_mesh`, not only from submodules ────
# An engine asking for a mesh interface should not have to know which FILE it lives in —
# `from iagent_mesh.interfaces import MeshVectors` makes the module path part of the contract,
# so moving the definition is a rename every consumer sees. R-038 applied to a module name.
#
# SAFE WITH RESPECT TO THE FASTAPI GUARD, checked rather than assumed: these three modules import
# only `typing` and `pydantic`, both already hard dependencies and neither a web framework. If a
# future edit gives one of them a server dependency, `test_the_sdk_imports_without_a_web_framework`
# reds — that seal imports the PACKAGE, so it covers every name added here.
from .conformance import (
    ConformanceFailure,
    assert_fixture_discriminates,
    check_embedding_contract,
    check_graph_writer_contract,
    check_graph_writer_delete_node_contract,
    check_graph_writer_has_edges_contract,
    check_graph_writer_has_node_contract,
    check_graph_writer_key_only_delete_contract,
    check_graph_writer_write_node_contract,
    check_live,
    check_offline,
    check_ontology_contract,
    check_ontology_writer_contract,
    check_vectors_writer_contract,
    check_vectors_writer_delete_contract,
    check_writer_marker,
    check_writer_offline,
)
from .rows import (
    HOLE_DISPOSITIONS,
    NON_HOLE_DISPOSITIONS,
    ROW_DISPOSITIONS,
    VERDICT_KEYS,
    disposition_for,
    fetch_row,
    has_content,
    holes_from,
    reachable_for,
    row,
    verdict_of,
)
from .edge_types import (
    REGISTRAR_EDGE_TYPES,
    TRACE_WRITER_EDGE_TYPES,
    UndeclaredWriteInterface,
    declared_edge_types,
)
from .enumeration import (
    DEFAULT_ENUMERATE_LIMIT,
    EnumerateInstancesRequest,
    EnumerateInstancesResponse,
    InstanceOption,
    over_limit,
    unhonoured_scoping,
)
from .interfaces import (
    MARKER_ASSERTS,
    MARKER_DOES_NOT_ASSERT,
    MESH_COLLECTION_META,
    CollectionMarker,
    CorruptCollectionMarker,
    DelegateIdentityRefused,
    EdgeIdentity,
    EdgeIdentityFilter,
    Embedder,
    Initiator,
    MeshGraph,
    MeshGraphWriter,
    MeshOntology,
    MeshOntologyWriter,
    MeshVectors,
    MeshVectorsWriter,
    ServiceIdentityRefused,
    collection_marker,
    marker_predates_collection,
    read_collection_marker,
)
from .results import (
    OUTCOMES,
    AmbiguousResultTruth,
    MeshResult,
    Outcome,
    ResultNotAnswered,
)
from .write_results import (
    WRITE_OUTCOMES,
    AmbiguousWriteResultTruth,
    MeshWriteResult,
    WriteNotApplied,
    WriteOutcome,
)

# THE PROVENANCE BLOCK, RE-EXPORTED AT ROOT — ordered 2026-09-30, unlike `delegate_identity` and
# `service_identity` which stay module-qualified. Those two are internal to the SDK's own
# identity machinery; this module is explicitly a cross-repo import surface — "a builder
# doc-tools can import" only reads as one import line (`from iagent_mesh import make_provenance`)
# if it resolves here, at the root, the same reason `EdgeIdentity` and `MeshGraphWriter` do.
from .provenance import (
    AS_OF_UNKNOWN,
    DIRECT,
    ETL,
    MANUAL_EXPORT,
    OBTAINED_VIA,
    PROV_DERIVED_FROM,
    PROV_GENERATED_AT,
    USER_DROP,
    WAREHOUSE,
    ObtainedVia,
    ProvenanceBlock,
    ProvenanceIncomplete,
    is_stale,
    make_provenance,
    require_provenance,
    validate_provenance,
)

# THE INGEST WIRE SHAPES, RE-EXPORTED AT ROOT for the same reason `provenance` is — `IngestRequest`
# is meant to be one wire shape two repos agree on, which only holds if it resolves from one
# import path. `compose`/`validate_dir` here are NOT promoted bare (they would collide with
# `graph_manifest`'s and `task_kinds`'s own same-named functions — see the 0.9.4 ruling comment
# above); `load_content_kind_registrations` is unambiguous and comes to the root instead.
from .ingest import (
    CONTENT_KIND_BRANCHES,
    INGEST_STAGES,
    ArtifactRevision,
    ContentKindBranch,
    ContentKindRegistration,
    ContentKindUnregistered,
    IngestRequest,
    IngestStage,
    IngestStatus,
    RefreshSpec,
    load_content_kind_registrations,
    registered_kinds,
    resolve_content_kind,
)

# ── THE THREE MODULES PROMOTED IN 0.9.4, MINUS FOUR NAMES THAT CANNOT COME ──────────────────
# `declarations`, `discovery` and `task_kinds` were public in their modules and absent from the
# root, and the reason recorded for the omission was never "these are internal" — it was that
# FOUR names are exported by two modules each and a root cannot mean both:
#
#     compose         graph_manifest   task_kinds
#     json_schema     graph_manifest   task_kinds
#     validate_dir    graph_manifest   task_kinds
#     resolve         discovery        task_kinds
#
# RULED (architect, 2026-09-19): those four are NEVER exported bare at the root. They stay
# module-qualified, on BOTH sides — `from iagent_mesh.task_kinds import compose`, and
# `from iagent_mesh.discovery import resolve`. The other sixteen names come to the root.
#
# `compose`, `json_schema` and `validate_dir` ALREADY resolve at this root, and they are
# graph_manifest's — imported above, shipped since 0.7.x, and consumed by
# agent_fleet/graph_host/main.py. Withdrawing them to satisfy the rule literally would be a
# SUBTRACTION from a published surface, which the same ruling forbids in its last line
# (additive only). So the rule binds where it can still bind: no NEW colliding name arrives
# here, and no existing one changes meaning. `resolve` is at the root from neither side,
# because neither side was ever here to be broken.
#
# THIS IS THE ONE PLACE THE SIXTEEN CAN SHADOW SOMETHING, so the seal in
# `test_every_public_name_is_reachable.py` no longer asks `hasattr` — it asks whether the root's
# binding IS the module's object. Under `hasattr`, `task_kinds.compose` reads as "reachable"
# while the root hands the caller graph_manifest's function, which is precisely the silent
# shadowing that file exists to prevent, wearing a green.
from .declarations import (
    DeclarationError,
    compose_rows,
    load_rows,
    read_rows,
)
from .discovery import (
    GROUPS,
    AmbiguousImplementation,
    NoImplementation,
    available,
)
from .task_kinds import (
    ARCHETYPES,
    KIND_PATTERN,
    UNDECLARED,
    RendersAs,
    Resolution,
    TaskKind,
    TaskKindError,
    load_task_kinds,
)

# THE SYSTEMS-OF-RECORD SCHEMA AND `Origin`, 0.9.7 — the architect's "ORIGIN, not audience"
# ruling, item 1. `compose`/`validate_dir` here are NOT promoted bare, for the same reason
# ingest's own aren't — see the 0.9.4 ruling comment above; this is the fifth family to collide
# on those two names, covered by the existing rule rather than a new carve-out.
from .systems_of_record import (
    RECORD,
    RESOLVED_BY,
    STEWARD,
    UNRESOLVED,
    ConnectorLookup,
    IdentityMatch,
    Origin,
    ResolvedBy,
    SystemOfRecord,
    SystemOfRecordConnector,
    UnknownConnector,
    load_systems_of_record,
    match_system_of_record,
    validate_connectors_known,
)

# The maintenance bridge wire shapes (0.9.8) — `MaintenanceEvent`/`ActionRecord`/
# `ApprovalChainEntry` and their nested rows, mirroring ADR-0046 §1/§4 per the week-1 contract
# packet. `CaseState` is deliberately absent — see the module docstring for why.
from .maintenance_bridge import (
    APPROVAL_OUTCOMES,
    EVENT_KINDS,
    EVENT_SOURCES,
    LEAD_TIME_SOURCES,
    STAND_IN,
    SUPPLY_SYSTEM,
    ActionProvenance,
    ActionRecord,
    ApprovalChainEntry,
    ApprovalOutcome,
    BattleCondition,
    BattleConditionBasis,
    EventKind,
    EventProvenanceRow,
    EventSource,
    EventSourceKind,
    Fault,
    LeadTimeSource,
    MaintenanceEvent,
    PartRow,
    Picture,
    ReleasabilityLabel,
    SpareRow,
    TaskRef,
    WorkOrder,
)

# `marker_is_stale` IS DELIBERATELY NOT RE-EXPORTED HERE. It is the deprecated alias for
# `marker_predates_collection`, and promoting a deprecated name into a NEW namespace extends its
# life rather than ending it — a caller who finds it at the package root has no reason to think
# it is on its way out. It stays importable from `iagent_mesh.interfaces` for the consumers that
# already use it, which is what the interval owes them, and no wider.

__all__ = [
    # the SOURCE_LEDGER row vocabulary (ADR-0046)
    "HOLE_DISPOSITIONS",
    "NON_HOLE_DISPOSITIONS",
    "ROW_DISPOSITIONS",
    "VERDICT_KEYS",
    "disposition_for",
    "fetch_row",
    "has_content",
    "holes_from",
    "reachable_for",
    "row",
    "verdict_of",
    # the write interfaces' edge-type registries
    "REGISTRAR_EDGE_TYPES",
    "TRACE_WRITER_EDGE_TYPES",
    "UndeclaredWriteInterface",
    "declared_edge_types",
    # the enumerate contract
    "DEFAULT_ENUMERATE_LIMIT",
    "EnumerateInstancesRequest",
    "EnumerateInstancesResponse",
    "InstanceOption",
    "over_limit",
    "unhonoured_scoping",
    # the interface surface (interfaces / results / conformance)
    "ConformanceFailure",
    "assert_fixture_discriminates",
    "check_embedding_contract",
    "check_graph_writer_contract",
    "check_graph_writer_delete_node_contract",
    "check_graph_writer_has_edges_contract",
    "check_graph_writer_has_node_contract",
    "check_graph_writer_key_only_delete_contract",
    "check_graph_writer_write_node_contract",
    "check_live",
    "check_offline",
    "check_ontology_contract",
    "check_ontology_writer_contract",
    "check_vectors_writer_contract",
    "check_vectors_writer_delete_contract",
    "check_writer_marker",
    "check_writer_offline",
    "MARKER_ASSERTS",
    "MARKER_DOES_NOT_ASSERT",
    "MESH_COLLECTION_META",
    "CollectionMarker",
    "CorruptCollectionMarker",
    "DelegateIdentityRefused",
    "EdgeIdentity",
    "EdgeIdentityFilter",
    "Embedder",
    "Initiator",
    "MeshGraph",
    "MeshGraphWriter",
    "MeshOntology",
    "MeshOntologyWriter",
    "MeshVectors",
    "MeshVectorsWriter",
    "ServiceIdentityRefused",
    "collection_marker",
    "marker_predates_collection",
    "read_collection_marker",
    "OUTCOMES",
    "AmbiguousResultTruth",
    "MeshResult",
    "Outcome",
    "ResultNotAnswered",
    "WRITE_OUTCOMES",
    "AmbiguousWriteResultTruth",
    "MeshWriteResult",
    "WriteNotApplied",
    "WriteOutcome",
    # the provenance block (ADR-0035 / ADR-0041 §2 — `user-drop`, the fifth `obtained_via` rung)
    "AS_OF_UNKNOWN",
    "DIRECT",
    "ETL",
    "MANUAL_EXPORT",
    "OBTAINED_VIA",
    "PROV_DERIVED_FROM",
    "PROV_GENERATED_AT",
    "USER_DROP",
    "WAREHOUSE",
    "ObtainedVia",
    "ProvenanceBlock",
    "ProvenanceIncomplete",
    "is_stale",
    "make_provenance",
    "require_provenance",
    "validate_provenance",
    # the ingest wire shapes (ADR-0021 content-kind selection / ADR-0041 user-drop ingest)
    "CONTENT_KIND_BRANCHES",
    "INGEST_STAGES",
    "ArtifactRevision",
    "ContentKindBranch",
    "ContentKindRegistration",
    "ContentKindUnregistered",
    "IngestRequest",
    "IngestStage",
    "IngestStatus",
    "RefreshSpec",
    "load_content_kind_registrations",
    "registered_kinds",
    "resolve_content_kind",
    "MeshClient",
    "MeshResponse",
    "CallerIdentity",
    "current_caller",
    "OutputShapes",
    "InputShapes",
    "Archetypes",
    "ARCHETYPE_BAML_NAME",
    "VERB_OUTPUT_URI",
    "GraphManifest",
    "SlotDecl",
    "ManifestError",
    "load_manifests",
    "compose",
    "validate_dir",
    "manifest_ref",
    "json_schema",
    "REFUSAL_DISPOSITIONS",
    "SLOT_KINDS",
    "ref_basis",
    "enforce_refusal",
    "RefusalViolation",
    "REF_COSMETIC",
    "registration_payload",
    "register_graph",
    # ── promoted in 0.9.4 ────────────────────────────────────────────────────────────────
    # Sixteen names, and the four absent ones are absent BY RULE rather than by oversight —
    # see the import block above and the _EXEMPT table in
    # tests/test_every_public_name_is_reachable.py, which names each with its reason.
    "DeclarationError",
    "compose_rows",
    "load_rows",
    "read_rows",
    "GROUPS",
    "AmbiguousImplementation",
    "NoImplementation",
    "available",
    "ARCHETYPES",
    "KIND_PATTERN",
    "UNDECLARED",
    "RendersAs",
    "Resolution",
    "TaskKind",
    "TaskKindError",
    "load_task_kinds",
    # the systems-of-record schema and `Origin` (0.9.7, "ORIGIN, not audience")
    "RECORD",
    "RESOLVED_BY",
    "STEWARD",
    "UNRESOLVED",
    "ConnectorLookup",
    "IdentityMatch",
    "Origin",
    "ResolvedBy",
    "SystemOfRecord",
    "SystemOfRecordConnector",
    "UnknownConnector",
    "load_systems_of_record",
    "match_system_of_record",
    "validate_connectors_known",
    # the maintenance bridge wire shapes (0.9.8) — ADR-0046 §1/§4 mirror; CaseState deliberately absent
    "APPROVAL_OUTCOMES",
    "EVENT_KINDS",
    "EVENT_SOURCES",
    "LEAD_TIME_SOURCES",
    "STAND_IN",
    "SUPPLY_SYSTEM",
    "ActionProvenance",
    "ActionRecord",
    "ApprovalChainEntry",
    "ApprovalOutcome",
    "BattleCondition",
    "BattleConditionBasis",
    "EventKind",
    "EventProvenanceRow",
    "EventSource",
    "EventSourceKind",
    "Fault",
    "LeadTimeSource",
    "MaintenanceEvent",
    "PartRow",
    "Picture",
    "ReleasabilityLabel",
    "SpareRow",
    "TaskRef",
    "WorkOrder",
]
