"""A concrete, HTTP-backed ``MeshGraph`` client — v0.9.13, built per
``sessions/2026-10-30-spec-v0-9-13-concrete-remote-clients.md``.

That spec is SPEC-ONLY: no gateway route named in it exists yet, and it files five open
questions for the gateway owner (invincible-agent) and the architect before a build should
start. This module is built anyway, against the spec's own "proposed shape" section as the
working default, per this task's instruction to build now and make every unresolved choice an
obvious, named default rather than a silent assumption. Each one is flagged at its call site
below. **None of this has been confirmed against a live gateway — every default here is this
lane's own choice, not a ruling.**

Flagged defaults, matching the spec's open-questions numbering:

1. (where routes live) — not this SDK's concern; untouched here.
2. **Identity on the wire** — ``Initiator`` is serialized with ``.model_dump(mode="json")``
   into the request body under an ``"initiator"`` key, passed through near-verbatim rather than
   mapped onto an existing Topaz-shaped auth header. This is CA's default pending the gateway
   owner's/architect's answer on which shape the gateway actually expects.
3. (SPARQL ownership) — N/A to this module; ``MeshOntology`` is out of scope tonight.
4. **``is_safety_critical`` folded in** — see the method below; flagged there, not hidden.
5. **Transport/error-mapping contract** — every ``httpx`` transport error (connection failure,
   timeout, ...) and every non-2xx HTTP response is mapped to ``MeshResult``'s existing
   ``unreachable`` outcome. This REUSES the state ``MeshGraph.providers_for`` already documents
   (registered / none-registered / unknown, with ``unreachable`` never cached) rather than
   inventing a new ``MeshResult`` variant — the spec's own open question 5 asked exactly whether
   a new state was needed; CA's answer, as a default, is no.

**Unflagged-but-also-undetermined: the gateway's response body shape.** No route exists to
observe, so this client assumes the gateway's JSON body mirrors ``MeshResult``'s own fields
(``outcome``/``rows``/``mode``/``detail``) and decodes with ``MeshResult(**payload)`` — the most
literal mapping available, and itself a default this lane is making, not a confirmed contract.
A payload that doesn't fit is treated as transport failure (``unreachable``), not a crash — see
open question 5's handling, applied here too since an un-decodable response is exactly as
unusable to the caller as an unreachable one.

Scope: ``MeshGraph`` only. The architect's 2026-10-30 overnight directive named "concrete
MeshGraph/MeshVectors clients" in one breath but also said "build graph first" — ``MeshVectors``
and ``MeshOntology`` clients are deliberately NOT built here.

No gateway route handler exists for any of these paths today. This client is a transport
adapter whose other end has not been built.
"""

from __future__ import annotations

from typing import Sequence

import httpx

from .interfaces import Initiator, MeshGraph
from .results import MeshResult

#: The fixed route prefix every operation hangs off, per the spec's proposed pattern
#: (``/mesh/graph/<operation>``, operation = the Protocol method's own snake_case name).
_ROUTE_PREFIX = "/mesh/graph"


class MeshGraphRemoteClient:
    """``MeshGraph``, implemented by one HTTP POST per method to a gateway that does not exist
    yet. Every method: serialize ``initiator`` plus its own typed args to JSON, POST to
    ``{base_url}/mesh/graph/<method name>``, map the response into ``MeshResult`` — no new
    fields, no behavior beyond that mapping, no domain-specific branching.

    The HTTP transport is INJECTED (``client: httpx.Client``) rather than constructed inside —
    this is what lets a test substitute a stub transport and never call a live gateway, and
    matches this SDK's existing synchronous ``httpx.Client`` convention (``client.py``,
    ``registration_transport.py``); nothing here is async.
    """

    #: This interface answers one way, so its results carry no mode — same declaration as the
    #: ``MeshGraph`` Protocol itself, kept consistent rather than silently dropped on the
    #: concrete class.
    MODES: tuple[str, ...] = ()

    def __init__(self, base_url: str, client: httpx.Client) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    # ── transport + mapping, shared by every operation ──────────────────────────────────────

    def _call(self, operation: str, body: dict) -> MeshResult:
        url = f"{self._base_url}{_ROUTE_PREFIX}/{operation}"
        try:
            response = self._client.post(url, json=body)
        except httpx.HTTPError as exc:
            # Flagged default (open question 5): any transport error maps to the existing
            # `unreachable` outcome rather than a new state or a raised exception.
            return MeshResult.unreachable(
                f"{operation}: transport error calling gateway: {type(exc).__name__}: {exc}"
            )
        if not (200 <= response.status_code < 300):
            # Flagged default (open question 5): a non-2xx status is treated the same as a
            # transport failure — the request never produced an answer the gateway stands by.
            detail = response.text[:500]
            return MeshResult.unreachable(
                f"{operation}: gateway returned HTTP {response.status_code}: {detail}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            return MeshResult.unreachable(
                f"{operation}: gateway response was not valid JSON: {exc}"
            )
        try:
            return MeshResult(**payload)
        except Exception as exc:  # noqa: BLE001 — a malformed body is a transport-shape
            # failure from this client's point of view, not a reason to crash the caller; the
            # assumed body shape (payload == MeshResult's own fields) is itself a flagged
            # default, documented at module level, not a confirmed gateway contract.
            return MeshResult.unreachable(
                f"{operation}: gateway response did not fit MeshResult: {exc}"
            )

    # ── MeshGraph, one method = one route ────────────────────────────────────────────────────

    def registry(self, initiator: Initiator) -> MeshResult:
        return self._call("registry", {"initiator": initiator.model_dump(mode="json")})

    def providers_for(self, initiator: Initiator, verb: str) -> MeshResult:
        return self._call(
            "providers_for",
            {"initiator": initiator.model_dump(mode="json"), "verb": verb},
        )

    def classes_with_a_verb(
        self, initiator: Initiator, domains: Sequence[str], *, include_referents: bool = False
    ) -> MeshResult:
        return self._call(
            "classes_with_a_verb",
            {
                "initiator": initiator.model_dump(mode="json"),
                "domains": list(domains),
                "include_referents": include_referents,
            },
        )

    def data_assets_for(self, initiator: Initiator, iri: str) -> MeshResult:
        return self._call(
            "data_assets_for",
            {"initiator": initiator.model_dump(mode="json"), "iri": iri},
        )

    def edge(self, initiator: Initiator, subject: str, verb: str) -> MeshResult:
        return self._call(
            "edge",
            {"initiator": initiator.model_dump(mode="json"), "subject": subject, "verb": verb},
        )

    def path(
        self, initiator: Initiator, start: str, end: str, *, cost_classes: Sequence[str]
    ) -> MeshResult:
        return self._call(
            "path",
            {
                "initiator": initiator.model_dump(mode="json"),
                "start": start,
                "end": end,
                "cost_classes": list(cost_classes),
            },
        )

    def operable_subjects(self, initiator: Initiator, domain: str) -> MeshResult:
        return self._call(
            "operable_subjects",
            {"initiator": initiator.model_dump(mode="json"), "domain": domain},
        )

    def verbs_for(self, initiator: Initiator, subject: str, *, max_hops: int) -> MeshResult:
        return self._call(
            "verbs_for",
            {
                "initiator": initiator.model_dump(mode="json"),
                "subject": subject,
                "max_hops": max_hops,
            },
        )

    def ancestors(self, initiator: Initiator, iri: str, *, max_hops: int) -> MeshResult:
        return self._call(
            "ancestors",
            {"initiator": initiator.model_dump(mode="json"), "iri": iri, "max_hops": max_hops},
        )

    def is_safety_critical(self, initiator: Initiator, *, mpn: str, domain: str) -> MeshResult:
        """Implemented here as an ordinary route, same mapping as every other method.

        **FLAGGED INFERENCE, not a fresh ruling.** The Protocol docstring
        (``iagent_mesh/interfaces.py``) says this stub was explicitly deferred — "type now,
        route later" — and that porting it "waits on a concrete `MeshGraph` client (v0.9.13)
        and an explicit producer wiring," adding "do not fold it into this route set without a
        fresh ruling naming it." No such ruling exists as a document. The architect's 2026-10-30
        overnight directive named "concrete MeshGraph/MeshVectors clients... build graph first"
        in the same breath as this method, and this build treats that juxtaposition as the
        naming the stub's own docstring asked for. That is an INFERENCE this lane is making
        under an explicit instruction to flag rather than hide it — not a claim that the
        producer-wiring question is settled. The route this calls
        (``POST {base_url}/mesh/graph/is_safety_critical``) does not exist on any gateway today,
        exactly like every other route in this module.
        """
        return self._call(
            "is_safety_critical",
            {"initiator": initiator.model_dump(mode="json"), "mpn": mpn, "domain": domain},
        )

# `MeshGraphRemoteClient` is a structural implementation of `MeshGraph` (the Protocol is
# `runtime_checkable`), but it is never declared `class MeshGraphRemoteClient(MeshGraph):` — a
# Protocol is matched by shape, not inherited, the same discipline every other `MeshGraph`
# caller in this SDK already assumes. `MeshGraph` is imported for `isinstance(obj, MeshGraph)`
# in this module's own tests, confirming the shape matches without declaring inheritance.
