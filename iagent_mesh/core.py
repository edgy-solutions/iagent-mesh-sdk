"""
``MeshTool`` — the SPO-shaped registration + execution wrapper for an
iagent mesh tool.

Per `ADR-0004 — Predicate-graph routing`_ and
`ADR-0005 — Two-class namespacing`_, a tool **is** a named, typed
predicate in the mesh's predicate graph:

.. code-block:: text

    (input_uri:OntologyClass) --[verb]--> (output_uri:OntologyClass)

The verb carries identity (its URI), the subject/object carry typing
(their concept classes), and the verb edge carries routing metadata
(endpoint URL, cost class, owner persona, etc.). The SDK lifespan
emits all of this to DataHub on startup; doc-tools' AITool binding
pipeline then syncs the predicate edge into Neo4j where Engine O's
``/find_tool`` and ``/find_path`` can discover it.

Per `ADR-0006 — DataHub inbox, Neo4j substrate`_, DataHub is the
proposal queue; the SDK never writes directly to Neo4j.

Registration is **opt-in** via ``MESH_REGISTER_ON_STARTUP=true`` so the
SDK is usable for local development without DataHub credentials.

.. _ADR-0004 — Predicate-graph routing: ../docs/adr/ADR-0004-predicate-graph-routing.md
.. _ADR-0005 — Two-class namespacing: ../docs/adr/ADR-0005-verb-and-concept-namespaces.md
.. _ADR-0006 — DataHub inbox, Neo4j substrate: ../docs/adr/ADR-0006-verb-registry-location.md
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import nest_asyncio
from fastapi import FastAPI, HTTPException, Request

# Allow nested event loops (e.g. agents using asyncio inside synchronous tool bodies).
nest_asyncio.apply()

from iagent_mesh.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MeshTool")

#: Supervisor uses ``cost_class`` to prefer cheap paths in multi-hop routing.
VALID_COST_CLASSES = frozenset({"fast", "medium", "slow"})

#: When ``MESH_REGISTER_ON_STARTUP`` matches one of these (case-insensitive),
#: the lifespan tries to emit a DataHub MCP. Otherwise it logs and skips —
#: keeps the SDK usable for local development without DataHub credentials.
_TRUTHY = {"true", "1", "yes", "on"}


class MeshTool:
    """SPO-shaped registration + execution wrapper for a mesh tool.

    Required arguments establish the predicate's identity and typing:

    :param name:        Short identifier used in the DataHub URN.
    :param description: Human-readable description; surfaces in DataHub UI
                        and in the tool's OpenAPI schema.
    :param verb:        Fully-qualified verb URI, e.g. ``"mesh:detectAnomalies"``
                        or ``"mro:applyDiagnostics"``. The prefix determines
                        ``namespace_authority`` per ADR-0005:
                        ``mesh:`` → ``"platform"``; anything else → ``"domain"``.
    :param input_uri:   ``rdfs:domain`` — the concept class this tool consumes.
                        Must be a namespaced URI (contain a ``:``).
    :param output_uri:  ``rdfs:range`` — the concept class this tool produces.
                        Must be a namespaced URI (contain a ``:``).

    Optional metadata informs supervisor routing and UI:

    :param verb_synonyms:           NL aliases for the verb
                                    (``rdfs:label`` / ``skos:altLabel``).
                                    Engine O's NL → verb classifier matches
                                    against these.
    :param owner_persona:           UI roster tag (e.g. ``"MECHANIC"``).
                                    Not used for routing, only for display.
    :param cost_class:              ``"fast" | "medium" | "slow"`` — supervisor
                                    composition prefers cheaper paths.
    :param requires_human_approval: If true, the supervisor pauses for HITL
                                    approval before invoking this tool.
    :param version:                 Semver-style string. Multiple versions of
                                    a tool can coexist as separate predicates.
    """

    def __init__(
        self,
        name: str,
        description: str,
        *,
        verb: str,
        input_uri: str,
        output_uri: str,
        verb_synonyms: Optional[list[str]] = None,
        owner_persona: Optional[str] = None,
        cost_class: str = "fast",
        requires_human_approval: bool = False,
        version: str = "0.1.0",
    ):
        self._validate(name, verb, input_uri, output_uri, cost_class)

        self.name = name
        self.description = description
        self.verb = verb
        self.input_uri = input_uri
        self.output_uri = output_uri
        self.verb_synonyms = list(verb_synonyms or [])
        self.owner_persona = owner_persona
        self.cost_class = cost_class
        self.requires_human_approval = requires_human_approval
        self.version = version

        # Per ADR-0005, ``mesh:`` is the reserved platform namespace. All other
        # prefixes are domain namespaces governed by their owning ontology.
        self.namespace_authority = "platform" if verb.startswith("mesh:") else "domain"

        # Use the standard DataHub ``mlModel`` entity type as the carrier --
        # it's the closest built-in primitive to "a callable that maps typed
        # input to typed output". Custom properties carry the mesh-specific
        # routing metadata. doc-tools filters on ``mesh_is_registration`` to
        # identify mesh tool entries (vs. real ML models on the same dataPlatform).
        self.urn = f"urn:li:mlModel:(urn:li:dataPlatform:mesh,{name},PROD)"

        self.app = FastAPI(
            title=self.urn,
            description=description,
            lifespan=self._lifespan,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate(
        name: str,
        verb: str,
        input_uri: str,
        output_uri: str,
        cost_class: str,
    ) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        if ":" not in verb:
            raise ValueError(
                f"verb must be a namespaced URI like 'mesh:foo' or 'mro:bar', "
                f"got: {verb!r}. See ADR-0005 for namespacing conventions."
            )
        if ":" not in input_uri:
            raise ValueError(
                f"input_uri must be a namespaced URI (e.g. 'mro:Symptom'), "
                f"got: {input_uri!r}. See ADR-0005."
            )
        if ":" not in output_uri:
            raise ValueError(
                f"output_uri must be a namespaced URI (e.g. 'mro:FaultReport'), "
                f"got: {output_uri!r}. See ADR-0005."
            )
        if cost_class not in VALID_COST_CLASSES:
            raise ValueError(
                f"cost_class must be one of {sorted(VALID_COST_CLASSES)}, "
                f"got: {cost_class!r}"
            )

    # ------------------------------------------------------------------
    # Lifespan / registration
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        # Opt-in: a local-dev tool should not require DataHub credentials.
        if os.getenv("MESH_REGISTER_ON_STARTUP", "false").lower() not in _TRUTHY:
            logger.info(
                "Skipping DataHub registration for %s "
                "(set MESH_REGISTER_ON_STARTUP=true to enable)",
                self.urn,
            )
            yield
            return

        logger.info("Registering %s to DataHub...", self.urn)
        try:
            self._emit_to_datahub(app.openapi())
            logger.info("✅ Successfully registered %s to DataHub.", self.urn)
        except Exception as e:  # noqa: BLE001  — registration failure must not crash the tool
            # Per ADR-0006, DataHub is the inbox; runtime serving happens
            # locally. A failed registration should NOT take the tool down.
            logger.warning(
                "⚠️ Failed to register %s to DataHub: %s. "
                "Tool will keep serving requests; routing will resume after "
                "the next successful registration cycle.",
                self.urn,
                e,
            )

        yield

        # No active deregistration: DataHub keeps the registration; doc-tools
        # syncs from there to Neo4j. If a tool is removed, its DataHub entry
        # is soft-deleted via a separate admin flow (out of scope for the SDK).

    def _emit_to_datahub(self, openapi_spec: dict) -> None:
        """Emit a single DataHub ``MetadataChangeProposalWrapper`` carrying
        the predicate-graph registration."""
        # Lazy import — keeps the dependency cost off of cold-start when
        # registration is disabled (the common dev case).
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.emitter.rest_emitter import DatahubRestEmitter
        from datahub.metadata.schema_classes import MLModelPropertiesClass

        gms_url = settings.DATAHUB_GMS_URL
        token = settings.DATAHUB_TOKEN

        if not gms_url:
            raise RuntimeError(
                "DATAHUB_GMS_URL must be set when MESH_REGISTER_ON_STARTUP=true"
            )

        endpoint_url = os.getenv(
            "MESH_TOOL_ENDPOINT", "http://localhost:8000/execute"
        )

        props = MLModelPropertiesClass(
            description=self.description,
            customProperties=self._registration_custom_properties(
                endpoint_url, openapi_spec
            ),
        )

        emitter = DatahubRestEmitter(gms_server=gms_url, token=token)
        mcp = MetadataChangeProposalWrapper(entityUrn=self.urn, aspect=props)
        emitter.emit(mcp)

    def _registration_custom_properties(
        self, endpoint_url: str, openapi_spec: dict
    ) -> dict[str, str]:
        """Build the ``customProperties`` dict for the DataHub aspect.

        DataHub requires all custom-property values to be strings — lists
        and dicts are JSON-encoded. doc-tools deserializes on the consume
        side.
        """
        return {
            # Marker for doc-tools' ``ingest_global_aitool_links`` to filter on.
            "mesh_is_registration":         "true",
            "mesh_tool_kind":               "AITool",
            # Predicate identity + typing
            "mesh_verb_iri":                self.verb,
            "mesh_verb_synonyms":           json.dumps(self.verb_synonyms),
            "mesh_input_uri":               self.input_uri,
            "mesh_output_uri":              self.output_uri,
            "mesh_namespace_authority":     self.namespace_authority,
            # Routing / policy metadata
            "mesh_owner_persona":           self.owner_persona or "",
            "mesh_cost_class":              self.cost_class,
            "mesh_requires_human_approval": "true" if self.requires_human_approval else "false",
            # Runtime
            "mesh_endpoint_url":            endpoint_url,
            "mesh_openapi_schema":          json.dumps(openapi_spec),
            # Versioning
            "mesh_sdk_version":             "0.1.0",
            "mesh_tool_version":            self.version,
        }

    # ------------------------------------------------------------------
    # Execution wiring
    # ------------------------------------------------------------------
    def execute(self):
        """Decorator that wires a Python function as the tool's ``/execute``
        handler. The function's first parameter's type annotation is used as
        the request-body Pydantic model."""

        def decorator(func):
            sig = inspect.signature(func)
            input_param = list(sig.parameters.values())[0]
            InputModel = input_param.annotation

            @self.app.post("/execute")
            async def route_handler(request: Request):
                # Platform: Topaz zero-trust check. Bypassed in LOCAL_DEV.
                auth_header = request.headers.get("Authorization")
                if not auth_header and not os.getenv("LOCAL_DEV"):
                    raise HTTPException(status_code=403, detail="Missing Topaz Ticket")

                # Validate and coerce the incoming JSON into the model.
                body = await request.json()
                try:
                    input_data = InputModel(**body)
                except Exception as e:
                    raise HTTPException(status_code=422, detail=str(e))

                # Execute. Both sync and async user functions are supported.
                try:
                    if inspect.iscoroutinefunction(func):
                        return await func(input_data)
                    return func(input_data)
                except Exception as e:  # noqa: BLE001
                    logger.error("Tool execution failed: %s", e)
                    raise HTTPException(status_code=500, detail="Internal Tool Error")

            return route_handler

        return decorator
