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

import contextvars
import functools
import inspect
import json
import logging
import os
import typing
from contextlib import asynccontextmanager
from typing import Callable, Optional

import nest_asyncio
from fastapi import FastAPI, HTTPException, Request

# Allow nested event loops (e.g. agents using asyncio inside synchronous tool bodies).
nest_asyncio.apply()

from iagent_mesh.config import settings
from iagent_mesh.transport_auth import CallerIdentity, current_caller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MeshTool")


def _sdk_version() -> str:
    """The INSTALLED version of this package, for registration provenance.

    Falls back to "unknown" rather than to a literal: a wrong version is indistinguishable from a
    right one downstream, whereas "unknown" is legible as missing metadata. Only reachable when
    the package is imported from a source tree with no distribution installed.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("iagent_mesh")
        except PackageNotFoundError:
            return version("iagent-mesh")
    except Exception:  # noqa: BLE001 — provenance must never break registration
        return "unknown"


async def _run_sync_in_threadpool(func, *args, **kwargs):
    """Run a blocking handler off the event loop, WITH the request context copied.

    THE DOC PROMISED THIS AND THE CODE DID NOT DO IT. `jupyter_guide.md` tells authors that a
    standard `def` handler crunching Polars "will execute safely in a background thread" and
    recommends it as the default for `df.collect()` — the heaviest workload. It ran inline on the
    event loop, so a multi-second `collect()` stalled every other request to that tool, health
    probes included. Authors who FOLLOWED the recommendation were worse off than authors who
    ignored it.

    THE CONTEXT COPY IS THE COUPLING. `contextvars.copy_context()` is taken on the event loop —
    where the transport-auth dependency has already published the caller — and the handler runs
    inside it via `ctx.run`, so `current_caller()` resolves in the worker thread. Done with a
    mechanism that does NOT copy context (`loop.run_in_executor` takes a bare callable), the
    caller would read `None` inside every sync handler and any code falling back to a process
    identity would silently read as the service. The two defects are fixed here in one place
    precisely because fixing them apart is what composes them into a cross-tenant read.

    `anyio.to_thread.run_sync` is used directly rather than Starlette's `run_in_threadpool`:
    both copy the context in current versions, but doing it explicitly makes the guarantee this
    function's correctness rests on visible at the call site instead of inherited from a
    dependency's implementation detail — and testable, which it is.
    """
    import anyio.to_thread

    ctx = contextvars.copy_context()
    return await anyio.to_thread.run_sync(functools.partial(ctx.run, functools.partial(func, *args, **kwargs)))

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
    :param verb_anti_synonyms:      NL phrases that should REPEL this verb
                                    from being selected. Per the ADR-0008
                                    follow-up on confidently-wrong routing,
                                    Engine O's ``/search_predicates`` does a
                                    post-filter re-rank that penalizes a
                                    candidate verb whose similarity to the
                                    query against ``verb_anti_synonyms`` is
                                    high. Use these for cases where
                                    ``verb_synonyms`` alone can't disambiguate
                                    — e.g. ``mesh:traceLineage`` is
                                    semantically close to catalog enumeration
                                    questions ("what tables do you have") but
                                    should not handle them; the right move is
                                    to list those exact phrasings as
                                    anti-synonyms here.
    :param owner_persona:           **Answerer persona** (engine-side) — the
                                    voice/shape the engine uses to respond.
                                    Per ADR-0009 this drives BAML response-
                                    union resolution and Engine F's UI
                                    archetype. NOT the user's persona.
    :param domains:                 Domain scopes this tool serves (e.g.
                                    ``["MAINTENANCE", "MANUFACTURING"]`` or
                                    ``["DATA_ENGINEERING"]``). Per ADR-0009
                                    domain is a scope filter, not a routing
                                    key — ``/find_tool`` filters predicate
                                    matches against the caller's entitled
                                    domains. Empty list / None means the
                                    tool is domain-agnostic.
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
        verb_anti_synonyms: Optional[list[str]] = None,
        owner_persona: Optional[str] = None,
        domains: Optional[list[str]] = None,
        cost_class: str = "fast",
        requires_human_approval: bool = False,
        version: str = "0.1.0",
        mint: Optional[Callable[[], str]] = None,
    ):
        self._validate(name, verb, input_uri, output_uri, cost_class)

        self.name = name
        self.description = description
        self.verb = verb
        self.input_uri = input_uri
        self.output_uri = output_uri
        self.verb_synonyms = list(verb_synonyms or [])
        self.verb_anti_synonyms = list(verb_anti_synonyms or [])
        self.owner_persona = owner_persona
        self.domains = list(domains or [])
        self.cost_class = cost_class
        self.requires_human_approval = requires_human_approval
        self.version = version

        # IDENTITY IS AN ARGUMENT — the SDK never resolves an engine's credentials from ambient
        # env on the engine's behalf. `mint` is a callable returning a bearer for THIS engine;
        # `None` means "register unauthenticated", which is the pre-0.3.1 behaviour and stops
        # working when the mesh flips REQUIRE_TRANSPORT_AUTH.
        self._mint = mint

        # Per ADR-0005, ``mesh:`` is the reserved platform namespace. All other
        # prefixes are domain namespaces governed by their owning ontology.
        self.namespace_authority = "platform" if verb.startswith("mesh:") else "domain"

        # Use the standard DataHub ``mlModel`` entity type as the carrier --
        # it's the closest built-in primitive to "a callable that maps typed
        # input to typed output". Custom properties carry the mesh-specific
        # routing metadata. doc-tools filters on ``mesh_is_registration`` to
        # identify mesh tool entries (vs. real ML models on the same dataPlatform).
        self.urn = f"urn:li:mlModel:(urn:li:dataPlatform:mesh,{name},PROD)"

        # TRANSPORT AUTH — applied at the FACTORY so every engine inherits it with zero
        # lines of engine code, the same way telemetry landed in the shim. Default posture
        # is OBSERVE: validate what arrives, log it, refuse nothing. A refusing default
        # here would deny every token-less caller fleet-wide on the next rebuild — the
        # retroactive-inheritance property is the hazard as well as the point.
        from fastapi import Depends
        from .transport_auth import announce, app_docs_kwargs, make_transport_auth_dependency
        announce(component=name)
        self.app = FastAPI(
            title=self.urn,
            description=description,
            lifespan=self._lifespan,
            dependencies=[Depends(make_transport_auth_dependency(component=name))],
            # Docs OFF in deployment (see app_docs_kwargs): /openapi.json, /docs and /redoc are
            # registered by FastAPI via Starlette's add_route, so app-level `dependencies=`
            # NEVER applies to them. They answered 200 unauthenticated under REQUIRE on a live
            # pod — CLOSED in 0.2.3 by not registering the routes at all. Opt back in for dev
            # with IAGENT_MESH_DOCS=1.
            **app_docs_kwargs(),
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

        # MESH_REGISTRAR_URL toggles between the gateway path (the
        # architecturally-correct way; the gateway handles DataHub emit +
        # Contract D validation centrally) and the direct DataHub path
        # (legacy; the SDK ships acryl-datahub and emits the MCP itself).
        # Engines migrate at their own pace by setting MESH_REGISTRAR_URL.
        registrar_url = os.getenv("MESH_REGISTRAR_URL", "").rstrip("/")
        target = (
            f"mesh-registrar ({registrar_url})"
            if registrar_url
            else "DataHub (direct)"
        )
        logger.info("Registering %s to %s...", self.urn, target)
        try:
            if registrar_url:
                self._emit_to_registrar(registrar_url, app.openapi())
            else:
                self._emit_to_datahub(app.openapi())
            logger.info("✅ Successfully registered %s to %s.", self.urn, target)
        except Exception as e:  # noqa: BLE001  — registration failure must not crash the tool
            # Per ADR-0006, DataHub is the inbox; runtime serving happens
            # locally. A failed registration should NOT take the tool down.
            logger.warning(
                "⚠️ Failed to register %s to %s: %s. "
                "Tool will keep serving requests; routing will resume after "
                "the next successful registration cycle.",
                self.urn,
                target,
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

    def _emit_to_registrar(self, registrar_url: str, openapi_spec: dict) -> None:
        """Register via the mesh-registrar gateway.

        The agent doesn't need to know DataHub's protocol or ship
        ``acryl-datahub`` — the gateway translates the manifest into a
        DataHub MCP and emits it, and enforces ADR-0019 Contract D
        (``input_uri``/``output_uri`` must resolve to real
        :OntologyClass nodes) at registration time. On Contract D
        rejection the gateway returns HTTP 422 with the offending
        URI(s); this method surfaces that as a registration failure
        the agent's lifespan logs.

        Engines opt into this path by setting ``MESH_REGISTRAR_URL`` to
        the gateway's service URL (e.g.
        ``http://iagent-mesh-registrar:8090``). When unset the SDK
        falls through to ``_emit_to_datahub`` — the legacy direct path
        — so engines migrate at their own pace.

        THE REBIND — CLOSED IN 0.3.1 (a934c61); the gap below no longer exists. This method used
        to be a second registration implementation — a bare ``httpx.post`` with no credential, no
        retry, and ``raise RuntimeError`` on any non-200 — living beside
        ``registration_transport.register_with_mesh``, which 0.3.0 added expressly to be THE one
        authenticated registration path. The platform bound the new transport; the SDK's own
        consumer, this method, was never converted. So every externally-scaffolded engine — the
        exact audience this package exists for — registered unminted and would have stopped under
        REQUIRE. It now mints through the one transport like every other caller.

        Building the seam is not the same as wiring the consumers to it. See
        ``[[consolidation-completes-at-the-last-consumer]]``.
        """
        from .registration_transport import register_with_mesh

        endpoint_url = os.getenv(
            "MESH_TOOL_ENDPOINT", "http://localhost:8000/execute"
        )

        # The manifest mirrors mesh-registrar's RegistrationManifest
        # pydantic model (agent_fleet/mesh_registrar/main.py).
        manifest = {
            "name": self.urn.split(",")[1] if "," in self.urn else self.urn,
            "verb_iri": self.verb,
            "input_uri": self.input_uri,
            "output_uri": self.output_uri,
            "endpoint_url": endpoint_url,
            "owner_persona": self.owner_persona or "",
            "domains": self.domains,
            "description": self.description,
            "verb_synonyms": self.verb_synonyms,
            "verb_anti_synonyms": self.verb_anti_synonyms,
            "cost_class": self.cost_class,
            "requires_human_approval": self.requires_human_approval,
            "version": getattr(self, "version", "0.1.0"),
            "openapi_schema": json.dumps(openapi_spec),
        }

        # ONE registration transport: the mint, the ADR-0006 retry semantics (422 permanent,
        # 5xx retry-safe, mint failure retried as transient infra) and a named failure all live
        # there. `mint=None` reproduces today's unauthenticated POST exactly — but now with retry
        # and a reason — so this rebind changes no behaviour for engines that pass no identity.
        # Registering without an identity remains LEGAL only for as long as the fleet is in
        # OBSERVE; it stops working at the flip, tracked as [[transport-flip]]. Pass `mint=` to
        # be ready for it.
        result = register_with_mesh(
            registrar_url, manifest, component=self.name, mint=self._mint,
        )
        if result.registered:
            return
        # `register_with_mesh` NEVER raises; it returns a named reason. Re-raising here keeps the
        # lifespan's existing handler — and its ADR-0006 "registration failure must not crash the
        # tool" contract — unchanged.
        raise RuntimeError(f"mesh-registrar registration failed: {result.reason}")

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
            "mesh_verb_anti_synonyms":      json.dumps(self.verb_anti_synonyms),
            "mesh_input_uri":               self.input_uri,
            "mesh_output_uri":              self.output_uri,
            "mesh_namespace_authority":     self.namespace_authority,
            # Routing / policy metadata
            "mesh_owner_persona":           self.owner_persona or "",
            # Per ADR-0009: domains are a scope filter, not a routing key.
            # JSON-encoded list (DataHub custom properties must be strings).
            "mesh_domains":                 json.dumps(self.domains),
            "mesh_cost_class":              self.cost_class,
            "mesh_requires_human_approval": "true" if self.requires_human_approval else "false",
            # Runtime
            "mesh_endpoint_url":            endpoint_url,
            "mesh_openapi_schema":          json.dumps(openapi_spec),
            # Versioning
            # READ FROM THE INSTALLED DISTRIBUTION, never a literal. This was hardcoded "0.1.0"
            # through releases 0.2.0 -> 0.3.1, so every registration in DataHub reported an SDK
            # version that had not been accurate for three releases — and `mesh_sdk_version` is
            # exactly the field an operator would consult to ask "which engines are still on a
            # pre-mint SDK?". A provenance field that cannot change is worse than absent: it
            # answers confidently and wrongly.
            "mesh_sdk_version":             _sdk_version(),
            "mesh_tool_version":            self.version,
        }

    # ------------------------------------------------------------------
    # Execution wiring
    # ------------------------------------------------------------------
    def execute(self, *, caller_scoped: Optional[bool] = None):
        """Decorator that wires a Python function as the tool's ``/execute`` handler.

        The first parameter's type annotation is the request-body Pydantic model.

        A parameter annotated :class:`~iagent_mesh.transport_auth.CallerIdentity` — by any name —
        receives WHO INVOKED THIS TOOL::

            @app.execute()
            def detect(data: AnomalyInput, caller: CallerIdentity) -> AnomalyOutput:
                client = CortexDataClient(originator_email=caller.require_authz_id())

        WHY THE PARAMETER EXISTS. The transport-auth dependency computed a `CallerIdentity` and
        FastAPI threw it away (app-level dependency return values are discarded), so a handler
        had nothing to put in `originator_email=` and its only working option was a bare
        constructor — which reads with the SERVICE's entitlements, for every user, with no
        symptom. Engine DA had to route around the SDK entirely, pulling `user_email` off the
        request payload, to do per-user reads correctly.

        Prefer `require_authz_id()` over `.authz_id` at a read: it refuses an unresolved caller
        instead of silently becoming the service. Handlers that do not read per-user data can
        omit the parameter entirely — nothing about the existing single-parameter form changes.

        SYNC HANDLERS RUN ON A THREAD, with the request context COPIED, so the contextvar-based
        `current_caller()` is readable inside them too. That coupling is not incidental: threading
        via a mechanism that does not copy context (`loop.run_in_executor`) would leave
        `current_caller()` reading `None` inside exactly the handler style the quickstart
        recommends — two correct-looking fixes composing into a cross-tenant read.
        """

        def decorator(func):
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            # ANNOTATIONS MUST BE RESOLVED, NEVER READ RAW. Under `from __future__ import
            # annotations` — PEP 563, the SDK's own house style and increasingly the default one
            # — every annotation is a STRING. Reading `input_param.annotation` directly then
            # yielded the *str* "MyInput", and `InputModel(**body)` became `"MyInput"(**body)`:
            # every request to such a tool 422'd with `'str' object is not callable`, a message
            # naming nothing the author wrote. The tool's own tests would pass while any module
            # with that one import at the top failed on every call.
            #
            # Same failure family as the `Request` import in transport_auth, and resolved the
            # same way: ask typing to resolve the strings against the function's real globals.
            try:
                hints = typing.get_type_hints(func)
            except Exception:  # noqa: BLE001 — an unresolvable hint must not break registration
                hints = {}

            def _annotation(p):
                return hints.get(p.name, p.annotation)

            input_param = params[0]
            InputModel = _annotation(input_param)
            if isinstance(InputModel, str):
                raise TypeError(
                    f"{func.__name__}: could not resolve the type annotation "
                    f"{InputModel!r} for parameter {input_param.name!r}. The request-body model "
                    "must be importable at module level (a class defined inside a function "
                    "cannot be resolved under `from __future__ import annotations`)."
                )

            # Which parameter (if any) wants the caller — matched by ANNOTATION, not by name, so
            # a handler may call it `caller`, `invoker`, or `who`.
            caller_params = [p.name for p in params[1:]
                             if _annotation(p) is CallerIdentity]

            # DECLARE THE SCOPING POSTURE, NEVER LEAVE IT IMPLIED.
            #
            # Making the caller REACHABLE was only half the fix. A handler that simply omits the
            # parameter is back in the original silent state — it cannot scope work to the
            # verified caller, and nothing says so. Silence is exactly what let the discarded
            # identity sit unnoticed, so omission is now ANNOUNCED, and an UNDECLARED omission
            # WARNS once at registration.
            #
            # The warning is escapable on purpose: `@app.execute(caller_scoped=False)` records
            # that the author considered it and meant it. A warning that cannot be switched off
            # by stating intent becomes noise, and noise is re-silencing by another route.
            #
            # WORDING IS DELIBERATELY NARROW. It does NOT claim such a tool "reads as the
            # service" — a handler may legitimately be scoped by a credential it is handed (the
            # `DataPointer.temporary_access_token` pattern) or read nothing at all. The precise,
            # always-true statement is that it CANNOT SCOPE TO THE VERIFIED CALLER.
            declared = caller_scoped
            scoped = bool(caller_params) or declared is True
            if scoped:
                how = (f"parameter {caller_params[0]!r}" if caller_params
                       else "current_caller() (declared)")
                logger.info("identity: CALLER-SCOPED via %s [%s]", how, self.name)
            elif declared is False:
                logger.info("identity: NOT caller-scoped, DECLARED [%s]", self.name)
            else:
                logger.warning(
                    "identity: NOT caller-scoped, UNDECLARED [%s] — %s() cannot scope its work "
                    "to the verified caller. Add a `caller: CallerIdentity` parameter (then use "
                    "caller.require_authz_id() at any read), or pass "
                    "@app.execute(caller_scoped=False) to record that this is intended.",
                    self.name, func.__name__,
                )

            @self.app.post("/execute")
            async def route_handler(request: Request):
                # PRESENCE-ONLY CHECK RETIRED — CLOSED IN 0.2.0 (68e28c0), history below.
                # It refused an absent header and accepted ANY value present — `Bearer
                # anything` passed — so it was a gate a manifest counts as present while it
                # verifies nothing. Replaced by the factory-level transport_auth dependency,
                # which VALIDATES the token and reports the caller's posture. LOCAL_DEV no
                # longer bypasses anything, because OBSERVE mode already refuses nothing —
                # see transport_auth for the OBSERVE -> REQUIRE flip that ends that.

                # Validate and coerce the incoming JSON into the model.
                body = await request.json()
                try:
                    input_data = InputModel(**body)
                except Exception as e:
                    raise HTTPException(status_code=422, detail=str(e))

                # The app-level dependency has already run and published the caller. Falling back
                # to an unresolved identity (rather than raising here) keeps OBSERVE's promise to
                # refuse nothing at the TRANSPORT layer; the refusal belongs at the read, where
                # `require_authz_id()` makes it explicit and legible.
                kwargs = {}
                if caller_params:
                    caller = current_caller() or CallerIdentity(
                        None, False, "no transport-auth dependency on this app"
                    )
                    kwargs = {name: caller for name in caller_params}

                # Execute. Both sync and async user functions are supported.
                try:
                    if inspect.iscoroutinefunction(func):
                        return await func(input_data, **kwargs)
                    return await _run_sync_in_threadpool(func, input_data, **kwargs)
                except HTTPException:
                    # A handler's own deliberate HTTP outcome — 403 from a refused read, 404 from
                    # a missing asset — is an ANSWER, not a crash. Collapsing it into the generic
                    # 500 below would tell the caller "internal error" for a decision the handler
                    # made on purpose, and would hide an authorization denial behind a status that
                    # invites a retry.
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.error("Tool execution failed: %s", e)
                    raise HTTPException(status_code=500, detail="Internal Tool Error")

            return route_handler

        return decorator
