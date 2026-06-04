"""Output-shape URI vocabulary for the predicate-graph routing layer.

Per ADR-0017, every engine in the fleet must declare a specific
``output_uri`` in its ``register_engine_to_mesh`` call and echo the
same URI in every ``AgentFinalResponse``. Engine F's ``/render_ui``
looks up ``(output_uri, mesh:rendersAs, ?)`` triples in the predicate
graph to pick a presentation deterministically, instead of asking an
LLM to classify the data shape.

This module is the authoritative Python-side reference for the URIs
that participate in that lookup. The predicate-graph itself remains
the runtime source of truth (engines and presentations advertise via
``register_engine_to_mesh`` / ``register_presentation_to_mesh``); this
module just gives engine code stringly-typed constants to import
instead of free-form strings.

Two namespaces live here:

- :class:`OutputShapes` — the response shapes engines produce. New
  engines add their output type here when they register. Generic
  values (``mesh:AgentResponse``, ``mesh:AgentTask``) are listed only
  as deprecated transition values; new code should never use them.
- :class:`Archetypes` — the presentation IRIs Engine F's capabilities
  map onto. These mirror the BAML archetype names but use the
  ``mesh:`` IRI scheme for predicate-graph addressability.

Adding a new shape is a vocabulary change, not a code change in
consumers: append the constant here and the registering engine /
presentation picks it up via import. Existing code that hard-codes a
string keeps working but is no longer audit-clean.

Per ADR-0005 the ``mesh:`` prefix denotes the platform-authority
namespace; domain-specific shapes use domain prefixes (e.g.
``maint:WorkOrderSummary``) and are NOT listed here.
"""

from __future__ import annotations


class OutputShapes:
    """IRIs for engine ``output_uri`` values.

    Group ordering reflects the per-verb decomposition outlined in
    ADR-0017 §1 (Engine A's six question shapes), followed by the
    pre-existing shapes from Engine DA and Engine W, then the
    deprecated transition values.

    All values are plain strings; this is a namespace class, not an
    Enum, because the predicate-graph treats them as IRIs and matches
    on string equality.
    """

    # Engine A — catalog Q&A decomposition (ADR-0017 §1).
    OWNERSHIP_FACT = "mesh:OwnershipFact"
    LINEAGE_TOPOLOGY = "mesh:LineageTopology"
    IMPACT_SET = "mesh:ImpactSet"
    SCHEMA_DESCRIPTION = "mesh:SchemaDescription"
    FRESHNESS_REPORT = "mesh:FreshnessReport"
    # Tag-conditional asset queries, including PII-with-exposure-context.
    # Cross-feature predicate composability (tag X AND condition Y) lives on
    # the verb regardless of tag value — PII is one instance.
    TAG_FILTER_RESULT = "mesh:TagFilterResult"
    # General "tell me about asset X" profile lookup — owner+tags+domain+
    # description+freshness rolled into one. Distinct from any single-
    # attribute lookup above; fills the "describe dataset" gap.
    ASSET_PROFILE = "mesh:AssetProfile"

    # Engine DA — dataset analysis (pre-existing, ADR-0013-aligned).
    DATASET_ANALYSIS_REPORT = "mesh:DatasetAnalysisReport"

    # Engine W — knowledge retrieval (pre-existing).
    KNOWLEDGE_RETRIEVAL_RESPONSE = "mesh:KnowledgeRetrievalResponse"

    # --- Deprecated transition values. ---
    # Carried only for the ADR-0017 fallback window during which
    # Engine A's generic ``mesh:analyzeWithCodeAgent`` verb is still
    # registered. New engines MUST NOT use these. The audit table
    # flags them.
    AGENT_RESPONSE = "mesh:AgentResponse"
    AGENT_TASK = "mesh:AgentTask"


class InputShapes:
    """IRIs for engine ``input_uri`` values.

    Symmetric counterpart to :class:`OutputShapes`. The six Engine A
    verbs from ADR-0017 §1 share one narrow input (asset name plus
    optional class) so they collapse into a single
    :attr:`CATALOG_ASSET_QUERY`.
    """

    # Engine A — six verbs share this narrow input.
    CATALOG_ASSET_QUERY = "mesh:CatalogAssetQuery"

    # Engine DA / Engine W — pre-existing specific inputs.
    DATASET_ANALYSIS_REQUEST = "mesh:DatasetAnalysisRequest"
    KNOWLEDGE_QUERY = "mesh:KnowledgeQuery"

    # --- Deprecated transition values. ---
    AGENT_TASK = "mesh:AgentTask"


class Archetypes:
    """IRIs for presentation archetypes (Engine F's BAML components).

    These mirror the BAML archetype enum but use the ``mesh:`` scheme
    so they can participate in ``(subject, mesh:rendersAs, object)``
    triples in the predicate graph. The :attr:`baml_name` mapping
    below resolves the IRI back to the BAML enum value Engine F
    actually passes to its renderer.
    """

    KNOWLEDGE_DOCUMENT = "mesh:KnowledgeDocument"
    ASSET_STATE_METRIC = "mesh:AssetStateMetric"
    PROCESS_TOPOLOGY = "mesh:ProcessTopology"
    HAZARD_DECLARATION = "mesh:HazardDeclaration"
    CHART_WIDGET = "mesh:ChartWidget"
    DIGITAL_TWIN_3D = "mesh:DigitalTwin3D"


#: IRI -> BAML archetype enum string. Engine F looks up the chosen
#: triple's ``mesh_object_uri``, resolves it here, and passes the BAML
#: name to its renderer. Centralized so the BAML-name change is a
#: one-line edit instead of a grep.
ARCHETYPE_BAML_NAME = {
    Archetypes.KNOWLEDGE_DOCUMENT:  "KNOWLEDGE_DOCUMENT",
    Archetypes.ASSET_STATE_METRIC:  "ASSET_STATE_METRIC",
    Archetypes.PROCESS_TOPOLOGY:    "PROCESS_TOPOLOGY",
    Archetypes.HAZARD_DECLARATION:  "HAZARD_DECLARATION",
    Archetypes.CHART_WIDGET:        "CHART_WIDGET",
    Archetypes.DIGITAL_TWIN_3D:     "DIGITAL_TWIN_3D",
}


#: Verb IRI -> ``output_uri`` declared for that verb. Used by Engine A
#: at request-handling time to look up which ``output_uri`` to echo
#: in ``AgentFinalResponse`` for the routed verb. Keeps the per-verb
#: prompt and the wire echo in sync without each prompt hard-coding
#: the string.
VERB_OUTPUT_URI = {
    "mesh:lookupOwnership":      OutputShapes.OWNERSHIP_FACT,
    "mesh:traceLineage":         OutputShapes.LINEAGE_TOPOLOGY,
    "mesh:assessImpact":         OutputShapes.IMPACT_SET,
    "mesh:findSchema":           OutputShapes.SCHEMA_DESCRIPTION,
    "mesh:checkFreshness":       OutputShapes.FRESHNESS_REPORT,
    "mesh:filterByTag":          OutputShapes.TAG_FILTER_RESULT,
    "mesh:describeAsset":        OutputShapes.ASSET_PROFILE,
    # Engine DA / Engine W.
    "mesh:analyzeDataset":       OutputShapes.DATASET_ANALYSIS_REPORT,
    "mesh:retrieveKnowledge":    OutputShapes.KNOWLEDGE_RETRIEVAL_RESPONSE,
    # Generic Engine A fallback (deprecated, removed when ADR-0017
    # transition window closes).
    "mesh:analyzeWithCodeAgent": OutputShapes.AGENT_RESPONSE,
}


__all__ = [
    "OutputShapes",
    "InputShapes",
    "Archetypes",
    "ARCHETYPE_BAML_NAME",
    "VERB_OUTPUT_URI",
]
