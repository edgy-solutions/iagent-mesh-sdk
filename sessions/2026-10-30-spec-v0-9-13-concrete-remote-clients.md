to: iagent-mesh-sdk/lane/ca (self) and invincible-agent (gateway owner)
cc: architect
from: iagent-mesh-sdk/lane/ca
date: 2026-10-30
re: v0.9.13 — concrete remote clients for MeshGraph/MeshVectors/MeshOntology, SPEC FIRST per the
    architect's 2026-10-30 ruling ("Concrete remote clients are v0.9.13, spec first.")

This is the spec owed now, in place of code — the architect's directive defers the implementation
itself to v0.9.13 but asks for the design up front. Nothing below is built. No gateway route
named below exists yet.

# Why this is spec-only, not code, today

Verified directly against `invincible-agent/src/iagent/gateway.py`:
`grep -ncE "weaviate|SPARQL|sparql" invincible-agent/src/iagent/gateway.py` → `0`. The gateway
holds a raw Neo4j driver and 14 bespoke Cypher call sites; there is no generic REST surface for
any of the three protocols `MeshGraph`/`MeshVectors`/`MeshOntology` abstract over. Each protocol
is implemented in-process by its owning engine today: `ontology_service/mesh_graph.py` +
`mesh_ontology.py` for the graph/ontology reads, `agent_fleet/utils/mesh_vectors.py` (shared
across engines, not `weaviate_expert`'s own) for vectors. A concrete SDK client that calls out
over HTTP needs routes that don't exist — this is cross-repo infrastructure work in
invincible-agent's gateway, not an SDK-only task, so it is specced here rather than designed
unilaterally into another repo's code.

# What a concrete client is, precisely

`iagent_mesh/interfaces.py` already declares `MeshGraph(Protocol)`, `MeshOntology(Protocol)`,
`MeshVectors(Protocol)` (names as currently declared — confirm exact set at build time) as
signature-only contracts: every method takes `initiator: Initiator` plus typed args and returns
`MeshResult`/`MeshWriteResult`, no implementation. "Concrete remote client" means a class
implementing one of these Protocols by making an HTTP call to a gateway route and mapping the
JSON response into the already-declared `MeshResult` shape — nothing more. It must not widen or
narrow the Protocol's existing surface; a route whose response doesn't fit the declared
`MeshResult` shape is a gateway-side bug to fix before the client ships, not a reason to loosen
the SDK's own contract.

# Proposed shape, generic-at-birth compliant

Per the architect's 2026-10-30 sharpened standing rule (`feedback_generic_at_birth`), the new
gateway routes must be generic mechanism, not domain-named:

- One route per PROTOCOL OPERATION, not per domain or engine. E.g. `POST /mesh/graph/edge`,
  `POST /mesh/graph/path`, `POST /mesh/graph/ask` (SPARQL ASK), `POST /mesh/graph/construct`
  (SPARQL CONSTRUCT), `POST /mesh/vectors/get`, `POST /mesh/vectors/list_by_kind` — named after
  the Protocol method they implement, never after a calling engine or a domain.
- Request/response bodies carry `initiator` (or its resolved identity) plus the method's own typed
  args, as data — a route must not branch on an domain/kind value in code; any domain-specific
  behavior is a registry lookup inside the route handler, not an `if domain == "..."` branch.
- The gateway's existing 14 bespoke Cypher call sites are the MIGRATION TARGET, not a template:
  each one is a candidate to retire into a generic `MeshGraph` route once that route exists, not
  a model for a 15th bespoke one.

# Open questions for the gateway owner (invincible-agent) and architect, before v0.9.13 build starts

1. **Where do these routes live?** A new router module in `invincible-agent/src/iagent/gateway.py`
   itself, or a new file alongside it? This SDK has no opinion on invincible-agent's own layout;
   asking rather than assuming.
2. **Auth/identity shape on the wire.** `Initiator` (`iagent_mesh/interfaces.py`) is the SDK's
   in-process identity type — does it serialize directly to JSON for a POST body, or does the
   gateway expect its own existing auth header/claim shape (Topaz subject, etc.) and the client
   maps `Initiator` onto that at the call site? This determines whether the concrete client needs
   its own identity-mapping layer or can pass `Initiator` through almost verbatim.
3. **Which engine owns the SPARQL surface behind `ask`/`construct`?** `ontology_service` holds
   `mesh_ontology.py` today — does a gateway route proxy directly to Fuseki, or does it stay
   routed through `ontology_service` as today's in-process callers do? Changes whether the gateway
   needs its own SPARQL client or just forwards.
4. **`is_safety_critical`** (added this cycle as a type-only `MeshGraph` stub, no implementation)
   is explicitly NOT part of this v0.9.13 scope — its own ruling is "type now, route later," a
   separate, later decision from the three protocols above. Do not fold it into this route set
   without a fresh ruling naming it.
5. **Timeout/retry/error-mapping contract.** A remote HTTP call can fail in ways an in-process
   call cannot (network partition, gateway restart, timeout). Does `MeshResult`'s existing
   failure shape already cover "unreachable" (per `MeshGraph.providers_for`'s existing
   three-state doctrine — registered / none-registered / unknown, with `unreachable` never
   cached), or does a remote client need a new, explicit transport-failure state the Protocol
   doesn't yet declare?

# What ca does once these are answered

Implement one thin HTTP client class per Protocol in a new module (working name
`iagent_mesh/remote_clients.py`, open to a better name at build time), each implementing exactly
the Protocol's declared methods, mapping gateway JSON to `MeshResult`/`MeshWriteResult`, with no
new behavior, no new fields, and no domain-specific branching — a pure transport adapter. Tests
exercise the mapping against a stubbed HTTP layer, not a live gateway.

Lane: iagent-mesh-sdk/lane/ca
