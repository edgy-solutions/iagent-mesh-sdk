"""The write-side conformance arms must go red on the implementations they exist to reject —
the same discipline as `test_the_ontology_conformance_arm_bites.py`, applied to the write half
ruled 2026-09-27.

THE DEFECT `check_ontology_writer_contract` EXISTS TO CATCH: a writer that reports `written`
while having inserted into Jena's DEFAULT graph, invisible to the mesh resolver — the exact
doc-tools defect named in `MeshOntology`'s own corrected docstring. A writer that only ASSERTS
scoping (never GRAPH-wraps) must make this arm red, and red for that specific reason.

Nothing here imports a driver; the store is a dict.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_ontology_writer_contract,
    check_writer_offline,
)
from iagent_mesh.interfaces import Initiator
from iagent_mesh.results import MeshResult
from iagent_mesh.write_results import MeshWriteResult

PERSON = Initiator(subject="alice", kind="person")
GRAPH = "ex:graph"
IRI = "ex:thing"


# ── an in-memory ontology + writer pair, scoped by construction ────────────────────────────

class _ScopedOntologyStore:
    """The reference pair: a dict keyed by (graph, iri). Broken variants below override upsert
    to land writes somewhere the read half cannot see when asked WITHIN the correct graph."""

    def __init__(self) -> None:
        self._by_graph: dict[tuple[str, str], list[str]] = {}

    def upsert(self, initiator: Initiator, *, graph: str, iri: str, triples) -> MeshWriteResult:
        initiator.require_person_or_delegate("ontology.upsert")
        if not graph.strip() or not iri.strip() or not triples:
            return MeshWriteResult.refused("empty graph, iri, or triples")
        self._by_graph[(graph, iri)] = list(triples)
        return MeshWriteResult.written()

    def ask(self, initiator: Initiator, *, iri: str, graph: str | None = None) -> MeshResult:
        initiator.require_person("ask")
        key = (graph, iri)
        if graph is not None and key in self._by_graph:
            return MeshResult.answered([iri])
        return MeshResult.empty()


def _run(store) -> None:
    check_ontology_writer_contract(
        call_upsert=lambda: store.upsert(PERSON, graph=GRAPH, iri=IRI, triples=[f"<{IRI}> a <ex:Class> ."]),
        call_ask_within_graph=lambda: store.ask(PERSON, iri=IRI, graph=GRAPH),
        call_ask_default_graph=lambda: store.ask(PERSON, iri=IRI, graph=None),
    )


# ── positive control ─────────────────────────────────────────────────────────────────────

def test_A_SCOPED_WRITER_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    _run(_ScopedOntologyStore())


# ── the defect this arm exists to catch ─────────────────────────────────────────────────

def test_A_WRITER_THAT_LANDS_UNSCOPED_IS_CAUGHT_EVEN_THOUGH_IT_REPORTS_written():
    """THE DOC-TOOLS DEFECT ITSELF. `upsert` reports `written` — the outcome alone is a lie the
    ask-based check must catch, not merely trust."""

    class LandsOnlyInDefaultGraph(_ScopedOntologyStore):
        def upsert(self, initiator, *, graph, iri, triples):
            initiator.require_person_or_delegate("ontology.upsert")
            self._by_graph[(None, iri)] = list(triples)  # ignores the caller's `graph` entirely
            return MeshWriteResult.written()

        def ask(self, initiator, *, iri, graph=None):
            initiator.require_person("ask")
            return MeshResult.answered([iri]) if (graph, iri) in self._by_graph else MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"ontology\.upsert.*WITHIN the graph.*not 'answered'"):
        _run(LandsOnlyInDefaultGraph())


def test_A_WRITER_WHOSE_UPSERT_DID_NOT_APPLY_IS_REFUSED_BEFORE_ASKING():
    class Refuses(_ScopedOntologyStore):
        def upsert(self, initiator, *, graph, iri, triples):
            return MeshWriteResult.refused("pretend the store is down")

    with pytest.raises(ConformanceFailure, match=r"ontology\.upsert.*did not apply"):
        _run(Refuses())


def test_A_WRITER_THAT_LEAKS_INTO_THE_DEFAULT_GRAPH_TOO_IS_CAUGHT():
    """A write correctly found WITHIN its own graph, but also visible from a default-graph ask —
    the substrate is not scoping the way the writer's own outcome implies."""

    class LeaksIntoDefaultGraphToo(_ScopedOntologyStore):
        def ask(self, initiator, *, iri, graph=None):
            initiator.require_person("ask")
            if graph is not None:
                return super().ask(initiator, iri=iri, graph=graph)
            return MeshResult.failed("simulated: the default graph is not actually empty here")

    with pytest.raises(ConformanceFailure, match=r"ontology\.upsert.*DEFAULT graph.*unscoped"):
        _run(LeaksIntoDefaultGraphToo())


def test_A_WRITER_THAT_STORES_NOTHING_IS_CAUGHT_BY_THE_FIXTURE_CHECK():
    """`written` reported, nothing persisted anywhere — both asks come back `empty`, which the
    fixture-discrimination check catches before either outcome is even read."""

    class Lost(_ScopedOntologyStore):
        def upsert(self, initiator, *, graph, iri, triples):
            initiator.require_person_or_delegate("ontology.upsert")
            return MeshWriteResult.written()  # never actually stores anything

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate.*'empty'"):
        _run(Lost())


# ── the fixture must discriminate ───────────────────────────────────────────────────────

def test_A_STORE_WHERE_BOTH_ASKS_ALWAYS_ANSWER_IS_REFUSED_AS_NON_DISCRIMINATING():
    """If the default-graph ask answers regardless of scoping, this arm cannot tell a scoped
    writer from an unscoped one — refused on the fixture, before the outcome is even read."""

    class AlwaysAnswers(_ScopedOntologyStore):
        def ask(self, initiator, *, iri, graph=None):
            initiator.require_person("ask")
            return MeshResult.answered([iri])

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run(AlwaysAnswers())


def test_A_STORE_WHERE_BOTH_ASKS_ARE_ALWAYS_EMPTY_IS_REFUSED_AS_NON_DISCRIMINATING():
    class AlwaysEmpty(_ScopedOntologyStore):
        def ask(self, initiator, *, iri, graph=None):
            initiator.require_person("ask")
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run(AlwaysEmpty())


# ── check_writer_offline: the NotImplementedError arm, not yet covered elsewhere ──────────
# (person/service/delegate admission and the wrong-return-type arms live in
# test_writer_interfaces.py, alongside the Protocol shape tests they share fixtures with.)

class _ConformingVectorsWriter:
    def write(self, initiator: Initiator, *, collection, id, text, domains=(), vector_required=True) -> MeshWriteResult:
        initiator.require_person_or_delegate("vectors.write")
        return MeshWriteResult.written()

    def relocate(self, initiator: Initiator, *, collection, id, vector) -> MeshWriteResult:
        initiator.require_person_or_delegate("vectors.relocate")
        return MeshWriteResult.written()


def test_A_NOT_IMPLEMENTED_OPERATION_IS_CAUGHT_BY_NAME():
    class Broken(_ConformingVectorsWriter):
        def write(self, initiator, *, collection, id, text, domains=(), vector_required=True):
            raise NotImplementedError

    with pytest.raises(ConformanceFailure, match=r"write.*not implemented"):
        check_writer_offline(
            Broken(),
            operations=[("write", lambda i: Broken().write(i, collection="c", id="1", text="t"))],
        )


def test_A_CONFORMING_VECTORS_WRITER_PASSES_BOTH_OPERATIONS():
    """POSITIVE CONTROL for the two-operation case — a suite that only ever tried one operation
    could not tell a writer that conforms on `write` but not `relocate` from a fully conforming
    one."""
    w = _ConformingVectorsWriter()
    check_writer_offline(
        w,
        operations=[
            ("write", lambda i: w.write(i, collection="c", id="1", text="t")),
            ("relocate", lambda i: w.relocate(i, collection="c", id="1", vector=[0.1, 0.2])),
        ],
    )
