"""``JenaOntologyWriter`` — the reference implementation of ``MeshOntologyWriter``, ruled 2026-09-27.

Fixes the defect ``doc-tools/lane/7f`` measured against sandbox Fuseki: three of its four
SPARQL-emitting plugins (``compliance.py``, ``maintenance.py``, ``manufacturing.py``) insert into
Jena's DEFAULT graph, invisible to the mesh resolver, because nothing at the write call forces
scoping (``doc-tools/sessions/2026-09-27-report-7f-mesh-jena-update-route-and-writer-inventory.md``,
Part 2). ``upsert()`` here has no path that skips the ``GRAPH`` clause: ``graph`` is a required
keyword, wrapped around every triple this writer emits, on BOTH the delete and the insert half of
the update. There is no second method, no optional graph, no raw-SPARQL passthrough — an unscoped
write is not a mistake a caller of this class could make, it is a call this class's surface cannot
express.

── THE ROUTE ────────────────────────────────────────────────────────────────────────────────
``POST update=<sparql>`` to ``{base_url}/{dataset}/update`` — measured live by ``doc-tools/lane/7f``
against sandbox Fuseki: 200, "Update succeeded". ``base_url``/``dataset`` are DECLARED to this
class's constructor, never derived by string substitution from a query endpoint: the
``endpoint.replace("/sparql", "/update")`` hazard was removed 2026-09-14 as a latent one, never an
observed failure (``agent_fleet/ontology_service/substrate_posture.py``, "DECLARED, NEVER
DERIVED"), and this writer does not reintroduce it.

── UPSERT IS DELETE-THEN-INSERT, ONE REQUEST, BOTH HALVES GRAPH-SCOPED ─────────────────────
A subject is identified by ``iri``; ``upsert()`` replaces every triple this writer previously put
there for that ``iri`` within ``graph`` with the newly supplied ``triples`` — one SPARQL Update
request carrying both a ``DELETE WHERE`` and an ``INSERT DATA``, not two round trips, so there is
no window in which the graph holds neither the old state nor the new one if the process dies
between them.

── WHY `graph` AND `iri` ARE VALIDATED RATHER THAN TRUSTED ─────────────────────────────────
Both are interpolated directly into a SPARQL IRI reference (``<...>``). A value containing ``<``,
``>`` or whitespace could close that reference early and inject additional triple patterns or
update clauses — the same class of defect as building SQL by string concatenation. ``triples`` is
NOT similarly escaped: the caller supplies already-formed triple statements (the same trust
boundary ``MeshOntology.construct`` already places on a caller reading Turtle text back), and this
writer's job is GRAPH-scoping, not becoming a second RDF serializer.
"""

from __future__ import annotations

from typing import Sequence

import httpx

from ..interfaces import Initiator, ServiceIdentityRefused
from ..write_results import MeshWriteResult

__all__ = ["JenaOntologyWriter"]

_ILLEGAL_IRI_CHARS = ("<", ">", " ", "\t", "\n", "\r")


def _reject_unsafe_iri_ref(label: str, value: str) -> str | None:
    """``None`` if ``value`` is safe to interpolate into ``<...>``; otherwise the refusal detail."""
    if not value.strip():
        return f"{label} is empty"
    for ch in _ILLEGAL_IRI_CHARS:
        if ch in value:
            return (
                f"{label} contains {ch!r}, which is not a legal character inside a SPARQL IRI "
                f"reference — refusing rather than interpolating it, since an IRI carrying '<', "
                f"'>' or whitespace could close the reference early and inject additional SPARQL"
            )
    return None


class JenaOntologyWriter:
    """Concrete ``MeshOntologyWriter`` over a Fuseki ``/update`` endpoint. GRAPH-wrapped, always.

    Structurally satisfies ``iagent_mesh.interfaces.MeshOntologyWriter`` (a ``runtime_checkable``
    Protocol) by matching its method — there is no inheritance here on purpose, the same
    structural-typing posture the read Protocols already use throughout this SDK.

    **EXPERIMENTAL, AS OF v0.9.5.** This is a reference implementation written and conformance-
    tested against the Protocol it satisfies; it has no caller in this fleet yet. The three writer
    Protocols it ships alongside (``MeshGraphWriter``, ``MeshVectorsWriter``, ``MeshOntologyWriter``
    itself) are stable contracts — this class is one implementation of one of them, not yet proven
    against a live Fuseki outside sandbox measurement. **First caller lands in 0.9.6.** Treat this
    class as a worked example of what satisfying ``MeshOntologyWriter`` looks like, not yet as a
    production dependency.
    """

    def __init__(self, *, base_url: str, dataset: str, timeout: float = 10.0) -> None:
        if not base_url.strip():
            raise ValueError("base_url is empty — a writer with nowhere to post is not a writer")
        if not dataset.strip():
            raise ValueError("dataset is empty")
        self._update_url = f"{base_url.rstrip('/')}/{dataset}/update"
        self._timeout = timeout

    def upsert(
        self, initiator: Initiator, *, graph: str, iri: str, triples: Sequence[str]
    ) -> MeshWriteResult:
        try:
            initiator.require_person_or_delegate("ontology.upsert")
        except ServiceIdentityRefused as exc:
            return MeshWriteResult.refused(str(exc))

        graph_problem = _reject_unsafe_iri_ref("graph", graph)
        if graph_problem is not None:
            return MeshWriteResult.refused(
                f"{graph_problem} — upsert() refuses an unscoped or malformed write rather than "
                f"defaulting to Jena's default graph, which is the exact defect this class "
                f"exists to make structurally impossible"
            )
        iri_problem = _reject_unsafe_iri_ref("iri", iri)
        if iri_problem is not None:
            return MeshWriteResult.refused(iri_problem)
        if not triples:
            return MeshWriteResult.refused(
                "no triples supplied — an upsert with nothing to insert is a delete wearing "
                "another name; this method does not perform deletes on its own"
            )

        sparql = (
            f"DELETE WHERE {{ GRAPH <{graph}> {{ <{iri}> ?mesh_p ?mesh_o }} }} ;\n"
            f"INSERT DATA {{ GRAPH <{graph}> {{ {' '.join(triples)} }} }}"
        )

        try:
            response = httpx.post(
                self._update_url, data={"update": sparql}, timeout=self._timeout
            )
        except httpx.RequestError as exc:
            return MeshWriteResult.unreachable(f"could not reach {self._update_url}: {exc}")

        # 502/503/504 are the substrate being unreachable through a proxy, not the update being
        # rejected — the same failed/unreachable split the read side draws, carried over here so
        # an operator sees a deployment problem as a deployment problem, not a query defect.
        if response.status_code in (502, 503, 504):
            return MeshWriteResult.unreachable(
                f"{self._update_url} returned {response.status_code}: {response.text[:500]}"
            )
        if response.status_code != 200:
            return MeshWriteResult.failed(
                f"{self._update_url} returned {response.status_code}: {response.text[:500]}"
            )
        return MeshWriteResult.written()
