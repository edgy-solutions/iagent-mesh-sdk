"""The write-side conformance arms must go red on the implementations they exist to reject —
the same discipline as `test_the_ontology_conformance_arm_bites.py`, applied to the write half
ruled 2026-09-27, to the two arms ruled 2026-09-28 overnight (`check_graph_writer_contract`,
`check_vectors_writer_contract`), and to the graph writer's amended identity/key shape ruled
2026-09-29 on the worker's own packet back.

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
    check_graph_writer_contract,
    check_graph_writer_has_edges_contract,
    check_graph_writer_key_only_delete_contract,
    check_graph_writer_write_node_contract,
    check_ontology_writer_contract,
    check_vectors_writer_contract,
    check_vectors_writer_delete_contract,
    check_writer_offline,
)
from iagent_mesh.interfaces import EdgeIdentity, EdgeIdentityFilter, Initiator
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


# ── check_graph_writer_contract, ruled 2026-09-28 overnight, amended 2026-09-29 ─────────────
#
# THE DEFECT THIS ARM EXISTS TO CATCH: a `write_edge` that reports `written` without the edge
# actually being reachable by a read — the write-side lie this arm proves does not survive being
# asked, the same discipline as the ontology arm above, adapted to a Protocol with no scope
# parameter to exploit. THE KEY ARM (added 2026-09-29, on the worker's own packet back) exists to
# catch a SECOND defect: a store that keys an edge on (subject, verb) alone, so a second write of
# the same triple under a different caller-supplied `key` silently overwrites the first instead of
# landing as a second edge.

class _EdgeStore:
    """The reference pair: a dict keyed by (subject, verb), holding every `key` written for that
    pair. Broken variants below override `write_edge` or `edge` to answer independently of what
    was actually written.

    Also holds `_nodes`, keyed by (label, id) — `write_node`'s own storage, added 2026-10-01.
    Separate dict from `_by_pair` on purpose: a node is not an edge, and conflating their storage
    would let a node-id collision with a (subject, verb) pair go unnoticed."""

    def __init__(self) -> None:
        self._by_pair: dict[tuple[str, str], dict[str, str]] = {}
        self._nodes: dict[tuple[str, str], dict[str, str]] = {}

    def write_edge(
        self, initiator: Initiator, *, identity: EdgeIdentity, payload=None
    ) -> MeshWriteResult:
        initiator.require_person_or_delegate("graph.write_edge")
        self._by_pair.setdefault((identity.subject, identity.verb), {})[identity.key] = (
            identity.object
        )
        return MeshWriteResult.written()

    def delete_edges(
        self, initiator: Initiator, *, identity_filter: EdgeIdentityFilter
    ) -> MeshWriteResult:
        initiator.require_person_or_delegate("graph.delete_edges")
        for pair, keyed in list(self._by_pair.items()):
            subject, verb = pair
            if identity_filter.subject not in (None, subject):
                continue
            if identity_filter.verb not in (None, verb):
                continue
            for key, obj in list(keyed.items()):
                if identity_filter.key not in (None, key):
                    continue
                if identity_filter.object not in (None, obj):
                    continue
                del keyed[key]
            if not keyed:
                del self._by_pair[pair]
        return MeshWriteResult.written()

    def edge(self, initiator: Initiator, subject: str, verb: str) -> MeshResult:
        initiator.require_person("edge")
        keyed = self._by_pair.get((subject, verb))
        if not keyed:
            return MeshResult.empty()
        return MeshResult.answered(list(keyed.values()))

    def has_edges(
        self, initiator: Initiator, *, identity_filter: EdgeIdentityFilter
    ) -> MeshResult:
        initiator.require_person_or_delegate("graph.has_edges")
        matches = []
        for (subject, verb), keyed in self._by_pair.items():
            if identity_filter.subject not in (None, subject):
                continue
            if identity_filter.verb not in (None, verb):
                continue
            for key, obj in keyed.items():
                if identity_filter.key not in (None, key):
                    continue
                if identity_filter.object not in (None, obj):
                    continue
                matches.append(obj)
        if not matches:
            return MeshResult.empty()
        return MeshResult.answered(matches)

    def write_node(
        self, initiator: Initiator, *, label: str, id: str, payload=None
    ) -> MeshWriteResult:
        initiator.require_person_or_delegate("graph.write_node")
        self._nodes[(label, id)] = dict(payload or {})
        return MeshWriteResult.written()


WRITTEN_SUBJECT, WRITTEN_VERB, WRITTEN_OBJECT = "ex:alice", "ex:knows", "ex:bob"
UNWRITTEN_SUBJECT, UNWRITTEN_VERB = "ex:carol", "ex:dislikes"
FIRST_KEY, SECOND_KEY = "_tool_urn:call-1", "_tool_urn:call-2"


def _run_graph(store) -> None:
    check_graph_writer_contract(
        call_write_edge=lambda: store.write_edge(
            PERSON,
            identity=EdgeIdentity(
                subject=WRITTEN_SUBJECT, verb=WRITTEN_VERB, object=WRITTEN_OBJECT, key=FIRST_KEY
            ),
        ),
        call_read_written_edge=lambda: store.edge(PERSON, WRITTEN_SUBJECT, WRITTEN_VERB),
        call_read_unwritten_edge=lambda: store.edge(PERSON, UNWRITTEN_SUBJECT, UNWRITTEN_VERB),
        call_write_edge_same_verb_different_key=lambda: store.write_edge(
            PERSON,
            identity=EdgeIdentity(
                subject=WRITTEN_SUBJECT, verb=WRITTEN_VERB, object=WRITTEN_OBJECT, key=SECOND_KEY
            ),
        ),
        call_read_edge_after_both_keys=lambda: store.edge(PERSON, WRITTEN_SUBJECT, WRITTEN_VERB),
        call_delete_edge_by_identity=lambda: store.delete_edges(
            PERSON,
            identity_filter=EdgeIdentityFilter(
                subject=WRITTEN_SUBJECT, verb=WRITTEN_VERB, key=FIRST_KEY
            ),
        ),
        call_read_edge_after_delete=lambda: store.edge(PERSON, WRITTEN_SUBJECT, WRITTEN_VERB),
    )


def test_G_A_CONFORMING_GRAPH_WRITER_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    _run_graph(_EdgeStore())


def test_G_A_WRITER_WHOSE_WRITE_DID_NOT_APPLY_IS_REFUSED_BEFORE_READING():
    class Refuses(_EdgeStore):
        def write_edge(self, initiator, *, identity, payload=None):
            return MeshWriteResult.refused("pretend the store is down")

    with pytest.raises(ConformanceFailure, match=r"graph\.write_edge.*did not apply"):
        _run_graph(Refuses())


def test_G_A_WRITER_THAT_STORES_NOTHING_IS_CAUGHT_BY_THE_FIXTURE_CHECK():
    """`written` reported, nothing persisted anywhere — both reads come back `empty`, which the
    fixture-discrimination check catches before either outcome is even read."""

    class Lost(_EdgeStore):
        def write_edge(self, initiator, *, identity, payload=None):
            initiator.require_person_or_delegate("graph.write_edge")
            return MeshWriteResult.written()  # never actually stores anything

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate.*'empty'"):
        _run_graph(Lost())


def test_G_A_SECOND_KEY_WRITE_THAT_DID_NOT_APPLY_IS_CAUGHT():
    """The first write and both reads pass; the SECOND key's write is refused — caught by name,
    before the row-count check that follows it is ever reached."""

    class RefusesSecondWrite(_EdgeStore):
        def __init__(self) -> None:
            super().__init__()
            self._writes = 0

        def write_edge(self, initiator, *, identity, payload=None):
            self._writes += 1
            if self._writes == 2:
                return MeshWriteResult.refused("pretend the second write is refused")
            return super().write_edge(initiator, identity=identity, payload=payload)

    with pytest.raises(ConformanceFailure, match=r"graph\.write_edge.*second write.*did not apply"):
        _run_graph(RefusesSecondWrite())


def test_G_A_WRITER_THAT_LETS_A_SECOND_KEY_OVERWRITE_THE_FIRST_IS_CAUGHT():
    """THE DEFECT THE WORKER'S PACKET NAMED: a store that keys an edge on (subject, verb) alone,
    ignoring `key` entirely, so the second write of the same triple silently overwrites the first
    instead of landing as a second edge. A read after both writes finds one row, not two."""

    class KeylessStore(_EdgeStore):
        def __init__(self) -> None:
            self._by_pair_single: dict[tuple[str, str], str] = {}

        def write_edge(self, initiator, *, identity, payload=None):
            initiator.require_person_or_delegate("graph.write_edge")
            self._by_pair_single[(identity.subject, identity.verb)] = identity.object
            return MeshWriteResult.written()

        def edge(self, initiator, subject, verb):
            initiator.require_person("edge")
            pair = (subject, verb)
            if pair in self._by_pair_single:
                return MeshResult.answered([self._by_pair_single[pair]])
            return MeshResult.empty()

    with pytest.raises(
        ConformanceFailure, match=r"one verb, two keys must yield two edges.*returned 1 row"
    ):
        _run_graph(KeylessStore())


def test_G_A_DELETE_THAT_DID_NOT_APPLY_IS_CAUGHT_BEFORE_READING():
    """Everything up to the delete passes; `delete_edges` itself is refused — caught by name,
    before the read-after-delete check that follows it is ever reached."""

    class RefusesDelete(_EdgeStore):
        def delete_edges(self, initiator, *, identity_filter):
            return MeshWriteResult.refused("pretend the delete is refused")

    with pytest.raises(ConformanceFailure, match=r"graph\.delete_edges.*did not apply"):
        _run_graph(RefusesDelete())


def test_G_A_DELETE_THAT_OVER_MATCHES_AND_REMOVES_BOTH_EDGES_IS_CAUGHT():
    """THE FAILURE ITEM 2 OF THE RULING EXISTS TO PREVENT: a `delete_edges` that ignores `key`
    (or any other bound field of the filter) and deletes every edge for the (subject, verb) pair
    regardless — the writer and the cleanup no longer agree on identity. A read after the delete
    finds zero rows, not the one that should have survived."""

    class DeleteIgnoresKey(_EdgeStore):
        def delete_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.delete_edges")
            self._by_pair.pop((identity_filter.subject, identity_filter.verb), None)
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"graph\.delete_edges.*over-matched"):
        _run_graph(DeleteIgnoresKey())


def test_G_A_DELETE_THAT_REPORTS_WRITTEN_BUT_DELETES_NOTHING_IS_CAUGHT():
    """The write-side lie, replayed on the delete path: `delete_edges` reports `written` and a
    read afterward proves nothing was actually removed — both edges are still there."""

    class DeleteIsANoOp(_EdgeStore):
        def delete_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.delete_edges")
            return MeshWriteResult.written()  # never actually deletes anything

    with pytest.raises(ConformanceFailure, match=r"graph\.delete_edges.*nothing was actually removed"):
        _run_graph(DeleteIsANoOp())


def test_G_A_STORE_WHERE_EDGE_ALWAYS_ANSWERS_IS_REFUSED_AS_NON_DISCRIMINATING():
    class AlwaysAnswers(_EdgeStore):
        def edge(self, initiator, subject, verb):
            initiator.require_person("edge")
            return MeshResult.answered([WRITTEN_OBJECT])

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run_graph(AlwaysAnswers())


def test_G_A_READ_THAT_CANNOT_FIND_THE_WRITTEN_EDGE_IS_CAUGHT():
    """The written pair reads back something other than 'answered', discriminating from the
    unwritten pair's genuine 'empty' — the write reported success and the read disagrees."""

    class CannotFindWhatWasWritten(_EdgeStore):
        def edge(self, initiator, subject, verb):
            initiator.require_person("edge")
            if (subject, verb) == (WRITTEN_SUBJECT, WRITTEN_VERB):
                return MeshResult.failed("simulated: the written edge is not actually readable")
            return super().edge(initiator, subject, verb)

    with pytest.raises(ConformanceFailure, match=r"graph\.write_edge.*just written.*not 'answered'"):
        _run_graph(CannotFindWhatWasWritten())


def test_G_A_READ_THAT_ANSWERS_FOR_AN_UNWRITTEN_EDGE_TOO_IS_CAUGHT():
    """The written pair reads back correctly, but the unwritten pair does NOT read back 'empty' —
    a read that cannot tell 'never written' from an error cannot prove the write above landed."""

    class UnwrittenReadErrorsInsteadOfEmpty(_EdgeStore):
        def edge(self, initiator, subject, verb):
            initiator.require_person("edge")
            if (subject, verb) == (UNWRITTEN_SUBJECT, UNWRITTEN_VERB):
                return MeshResult.failed("simulated: the store errors on this pair instead of "
                                          "answering empty")
            return super().edge(initiator, subject, verb)

    with pytest.raises(ConformanceFailure, match=r"graph\.write_edge.*never written.*not 'empty'"):
        _run_graph(UnwrittenReadErrorsInsteadOfEmpty())


# ── check_graph_writer_has_edges_contract, added 2026-09-30 on the promotion adapter's
# rejection packet back (ia-74/lane/74) ─────────────────────────────────────────────────────

def _run_has_edges(store) -> None:
    check_graph_writer_has_edges_contract(
        call_write_edge=lambda: store.write_edge(
            PERSON,
            identity=EdgeIdentity(
                subject=WRITTEN_SUBJECT, verb=WRITTEN_VERB, object=WRITTEN_OBJECT, key=FIRST_KEY
            ),
        ),
        call_has_edges_matching=lambda: store.has_edges(
            PERSON, identity_filter=EdgeIdentityFilter(key=FIRST_KEY)
        ),
        call_has_edges_not_matching=lambda: store.has_edges(
            PERSON, identity_filter=EdgeIdentityFilter(key="_tool_urn:never-written")
        ),
    )


def test_G_HAS_EDGES_A_CONFORMING_GRAPH_WRITER_PASSES():
    """POSITIVE CONTROL."""
    _run_has_edges(_EdgeStore())


def test_G_HAS_EDGES_THAT_ALWAYS_ANSWERS_IS_REFUSED_AS_NON_DISCRIMINATING():
    class AlwaysAnswers(_EdgeStore):
        def has_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.has_edges")
            return MeshResult.answered([WRITTEN_OBJECT])

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run_has_edges(AlwaysAnswers())


def test_G_HAS_EDGES_THAT_CANNOT_FIND_THE_WRITTEN_EDGE_IS_CAUGHT():
    class CannotFind(_EdgeStore):
        def has_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.has_edges")
            if identity_filter.key == FIRST_KEY:
                return MeshResult.failed("simulated: the written edge is not actually findable")
            return super().has_edges(initiator, identity_filter=identity_filter)

    with pytest.raises(ConformanceFailure, match=r"graph\.has_edges.*not 'answered'"):
        _run_has_edges(CannotFind())


def test_G_HAS_EDGES_THAT_ANSWERS_FOR_AN_UNWRITTEN_KEY_TOO_IS_CAUGHT():
    class AnswersForUnwritten(_EdgeStore):
        def has_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.has_edges")
            if identity_filter.key == "_tool_urn:never-written":
                return MeshResult.failed("simulated: errors instead of answering empty")
            return super().has_edges(initiator, identity_filter=identity_filter)

    with pytest.raises(ConformanceFailure, match=r"graph\.has_edges.*not 'empty'"):
        _run_has_edges(AnswersForUnwritten())


# ── check_graph_writer_key_only_delete_contract, added 2026-09-30 — the property the
# ingest_id cleanup convention depends on ──────────────────────────────────────────────────

SHARED_KEY = "ingest:2026-09-30-001"
TRIPLE_A = ("ex:fact-a-subject", "ex:fact-a-verb", "ex:fact-a-object")
TRIPLE_B = ("ex:fact-b-subject", "ex:fact-b-verb", "ex:fact-b-object")


def _run_key_only_delete(store) -> None:
    check_graph_writer_key_only_delete_contract(
        call_write_edge_a=lambda: store.write_edge(
            PERSON,
            identity=EdgeIdentity(
                subject=TRIPLE_A[0], verb=TRIPLE_A[1], object=TRIPLE_A[2], key=SHARED_KEY
            ),
        ),
        call_write_edge_b_same_key_different_triple=lambda: store.write_edge(
            PERSON,
            identity=EdgeIdentity(
                subject=TRIPLE_B[0], verb=TRIPLE_B[1], object=TRIPLE_B[2], key=SHARED_KEY
            ),
        ),
        call_delete_by_key_only=lambda: store.delete_edges(
            PERSON, identity_filter=EdgeIdentityFilter(key=SHARED_KEY)
        ),
        call_read_edge_a_after_delete=lambda: store.edge(PERSON, TRIPLE_A[0], TRIPLE_A[1]),
        call_read_edge_b_after_delete=lambda: store.edge(PERSON, TRIPLE_B[0], TRIPLE_B[1]),
    )


def test_G_KEY_ONLY_DELETE_A_CONFORMING_GRAPH_WRITER_PASSES():
    """POSITIVE CONTROL. `_EdgeStore.delete_edges` already treats an unbound subject/verb as a
    wildcard, so a key-only filter already reaches both triples here — this is the proof."""
    _run_key_only_delete(_EdgeStore())


def test_G_KEY_ONLY_DELETE_THAT_SCOPES_TO_ONE_PAIR_IS_CAUGHT():
    """THE EXACT GAP THIS ARM EXISTS TO CATCH: a store that indexes deletes by (subject, verb)
    first and treats `key` as a secondary filter WITHIN that pair, so a key-only filter (no
    subject/verb bound) silently matches nothing because no (subject, verb) pair was named."""

    class ScopesDeleteToNamedPairOnly(_EdgeStore):
        def delete_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.delete_edges")
            if identity_filter.subject is None or identity_filter.verb is None:
                return MeshWriteResult.written()  # BUG: silently matches nothing
            return super().delete_edges(initiator, identity_filter=identity_filter)

    with pytest.raises(
        ConformanceFailure, match=r"graph\.delete_edges \(key-only\).*edge A.*not 'empty'"
    ):
        _run_key_only_delete(ScopesDeleteToNamedPairOnly())


def test_G_KEY_ONLY_DELETE_THAT_REACHES_ONLY_THE_FIRST_MATCHING_PAIR_IS_CAUGHT():
    """A delete that reaches edge A (the first pair it iterates to) but stops there instead of
    continuing to every edge sharing the key — edge B is left behind."""

    class StopsAfterFirstMatch(_EdgeStore):
        def delete_edges(self, initiator, *, identity_filter):
            initiator.require_person_or_delegate("graph.delete_edges")
            for pair, keyed in list(self._by_pair.items()):
                for key in list(keyed.keys()):
                    if identity_filter.key not in (None, key):
                        continue
                    del keyed[key]
                    if not keyed:
                        del self._by_pair[pair]
                    return MeshWriteResult.written()  # BUG: returns after the first match
            return MeshWriteResult.written()

    with pytest.raises(
        ConformanceFailure, match=r"graph\.delete_edges \(key-only\).*edge B.*not 'empty'"
    ):
        _run_key_only_delete(StopsAfterFirstMatch())


# ── check_vectors_writer_contract, ruled 2026-09-28 overnight ───────────────────────────────
#
# THE DEFECT THIS ARM EXISTS TO CATCH: `vector_required`'s default (`True`) silently completing a
# write with no vector when the embed fails — the sixty-seven-day silent-BM25 defect replayed at
# write time — and a `relocate` that either accepts a dimension it cannot serve or quietly
# re-embeds instead of storing the precomputed vector it was given.

class _CountingEmbedder:
    """`should_fail` controls whether `embed` raises. `calls` increments before any raise, so a
    broken `relocate` that calls `embed` and swallows the exception is still caught."""

    def __init__(self, *, should_fail: bool, dimension: int = 3) -> None:
        self.calls = 0
        self.should_fail = should_fail
        self._dimension = dimension

    def embed(self, text: str):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("embed endpoint down")
        return [0.1] * self._dimension

    def identity(self):
        return ("test-model", "v1", self._dimension)


class _VectorsStore:
    """The reference pair: `write` refuses on a failed embed unless opted out; `relocate` refuses
    a dimension mismatch and never touches the Embedder."""

    def __init__(self, embedder: _CountingEmbedder) -> None:
        self._embedder = embedder
        self._store: dict[tuple[str, str], object] = {}

    def write(self, initiator: Initiator, *, collection, id, text, domains=(), vector_required=True) -> MeshWriteResult:
        initiator.require_person_or_delegate("vectors.write")
        try:
            vector = self._embedder.embed(text)
        except Exception as exc:
            if vector_required:
                return MeshWriteResult.refused(f"embed failed: {exc}")
            self._store[(collection, id)] = None
            return MeshWriteResult.written_without_vector(f"embed failed: {exc}")
        self._store[(collection, id)] = vector
        return MeshWriteResult.written()

    def relocate(self, initiator: Initiator, *, collection, id, vector) -> MeshWriteResult:
        initiator.require_person_or_delegate("vectors.relocate")
        _, _, dimension = self._embedder.identity()
        if len(vector) != dimension:
            return MeshWriteResult.refused(f"vector has {len(vector)} dims, writer is {dimension}")
        self._store[(collection, id)] = list(vector)
        return MeshWriteResult.written()

    def delete(self, initiator: Initiator, *, collection, id) -> MeshWriteResult:
        initiator.require_person_or_delegate("vectors.delete")
        self._store.pop((collection, id), None)
        return MeshWriteResult.written()


GOOD_VECTOR = [0.1, 0.2, 0.3]
WRONG_VECTOR = [0.1, 0.2]


def _run_vectors(store, embedder) -> None:
    check_vectors_writer_contract(
        call_write_with_failing_embedder=lambda: store.write(PERSON, collection="c", id="1", text="t"),
        call_write_with_failing_embedder_opted_out=lambda: store.write(
            PERSON, collection="c", id="2", text="t", vector_required=False
        ),
        call_relocate_matching_dimension=lambda: store.relocate(
            PERSON, collection="c", id="3", vector=GOOD_VECTOR
        ),
        call_relocate_wrong_dimension=lambda: store.relocate(
            PERSON, collection="c", id="4", vector=WRONG_VECTOR
        ),
        embed_call_count=lambda: embedder.calls,
    )


def test_V_A_CONFORMING_VECTORS_WRITER_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    embedder = _CountingEmbedder(should_fail=True)
    _run_vectors(_VectorsStore(embedder), embedder)


def test_V_A_WRITER_THAT_SILENTLY_COMPLETES_WITHOUT_A_VECTOR_BY_DEFAULT_IS_CAUGHT():
    """THE DEFECT ITSELF: `vector_required`'s default is `True`, and this writer ignores it,
    reporting a clean `written` for a text that never embedded."""

    embedder = _CountingEmbedder(should_fail=True)

    class IgnoresVectorRequired(_VectorsStore):
        def write(self, initiator, *, collection, id, text, domains=(), vector_required=True):
            initiator.require_person_or_delegate("vectors.write")
            try:
                self._embedder.embed(text)
            except Exception as exc:
                if vector_required:
                    return MeshWriteResult.written()  # BUG: ignores the failed embed on default
                return MeshWriteResult.written_without_vector(f"embed failed: {exc}")
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"vectors\.write.*DEFAULT.*applied"):
        _run_vectors(IgnoresVectorRequired(embedder), embedder)


def test_V_A_WRITER_THAT_IGNORES_THE_OPT_OUT_IS_CAUGHT_BY_THE_FIXTURE_CHECK():
    """The opt-out is never honoured — both calls refuse, indistinguishably."""

    embedder = _CountingEmbedder(should_fail=True)

    class IgnoresOptOut(_VectorsStore):
        def write(self, initiator, *, collection, id, text, domains=(), vector_required=True):
            initiator.require_person_or_delegate("vectors.write")
            try:
                self._embedder.embed(text)
            except Exception as exc:
                return MeshWriteResult.refused(f"embed failed: {exc}")  # ignores vector_required
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run_vectors(IgnoresOptOut(embedder), embedder)


def test_V_A_WRITER_THAT_LIES_ABOUT_VECTOR_PRESENCE_ON_OPT_OUT_IS_CAUGHT():
    """The opted-out write lands but reports a clean `written` instead of naming the vectorless
    state — the caller can no longer tell this write apart from one that actually embedded."""

    embedder = _CountingEmbedder(should_fail=True)

    class LiesAboutVectorPresence(_VectorsStore):
        def write(self, initiator, *, collection, id, text, domains=(), vector_required=True):
            initiator.require_person_or_delegate("vectors.write")
            try:
                self._embedder.embed(text)
            except Exception as exc:
                if vector_required:
                    return MeshWriteResult.refused(f"embed failed: {exc}")
                return MeshWriteResult.written()  # BUG: should be written_without_vector
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"vectors\.write.*not 'written_without_vector'"):
        _run_vectors(LiesAboutVectorPresence(embedder), embedder)


def test_V_A_RELOCATE_THAT_ACCEPTS_ANY_DIMENSION_IS_CAUGHT_BY_THE_FIXTURE_CHECK():
    """Both a matching and a mismatched vector are stored and report `written`, indistinguishably —
    the fixture cannot discriminate, which is itself the defect: dimension is never checked."""

    embedder = _CountingEmbedder(should_fail=True)

    class AcceptsAnyDimension(_VectorsStore):
        def relocate(self, initiator, *, collection, id, vector):
            initiator.require_person_or_delegate("vectors.relocate")
            self._store[(collection, id)] = list(vector)
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run_vectors(AcceptsAnyDimension(embedder), embedder)


def test_V_A_RELOCATE_THAT_FLAGS_A_MISMATCH_BUT_STILL_APPLIES_IT_IS_CAUGHT():
    """The mismatch is at least reported differently (`written_without_vector`) — enough to
    discriminate — but the vector is stored anyway, which is still wrong: it is not retrievable
    at the writer's declared dimension."""

    embedder = _CountingEmbedder(should_fail=True)

    class StillStoresTheMismatch(_VectorsStore):
        def relocate(self, initiator, *, collection, id, vector):
            initiator.require_person_or_delegate("vectors.relocate")
            _, _, dimension = self._embedder.identity()
            self._store[(collection, id)] = list(vector)
            if len(vector) != dimension:
                return MeshWriteResult.written_without_vector("dimension mismatch but stored anyway")
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"vectors\.relocate.*WRONG dimension.*applied"):
        _run_vectors(StillStoresTheMismatch(embedder), embedder)


def test_V_A_RELOCATE_THAT_ERRORS_EVEN_ON_A_MATCHING_DIMENSION_IS_CAUGHT():
    embedder = _CountingEmbedder(should_fail=True)

    class ErrorsOnMatchingDimension(_VectorsStore):
        def relocate(self, initiator, *, collection, id, vector):
            initiator.require_person_or_delegate("vectors.relocate")
            _, _, dimension = self._embedder.identity()
            if len(vector) == dimension:
                return MeshWriteResult.failed("simulated store error even on a matching dimension")
            return MeshWriteResult.refused(f"vector has {len(vector)} dims, writer is {dimension}")

    with pytest.raises(ConformanceFailure, match=r"vectors\.relocate.*must accept a vector"):
        _run_vectors(ErrorsOnMatchingDimension(embedder), embedder)


def test_V_A_RELOCATE_THAT_RE_EMBEDS_IS_CAUGHT():
    """Outcomes are all correct — the defect is only visible by counting Embedder calls."""

    embedder = _CountingEmbedder(should_fail=True)

    class ReEmbeds(_VectorsStore):
        def relocate(self, initiator, *, collection, id, vector):
            initiator.require_person_or_delegate("vectors.relocate")
            try:
                self._embedder.embed("relocate should never call this")  # BUG
            except Exception:
                pass
            _, _, dimension = self._embedder.identity()
            if len(vector) != dimension:
                return MeshWriteResult.refused(f"vector has {len(vector)} dims, writer is {dimension}")
            self._store[(collection, id)] = list(vector)
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"vectors\.relocate.*Embedder was called"):
        _run_vectors(ReEmbeds(embedder), embedder)


# ── check_vectors_writer_delete_contract, added 2026-09-30 on the promotion adapter's
# rejection packet back (ia-74/lane/74) ─────────────────────────────────────────────────────

DELETE_COLLECTION = "c"
WRITTEN_ID, NEVER_WRITTEN_ID = "written-id", "never-written-id"


def _run_vectors_delete(store, embedder) -> None:
    check_vectors_writer_delete_contract(
        call_write=lambda: store.write(
            PERSON, collection=DELETE_COLLECTION, id=WRITTEN_ID, text="t"
        ),
        call_delete_written=lambda: store.delete(
            PERSON, collection=DELETE_COLLECTION, id=WRITTEN_ID
        ),
        call_delete_never_written=lambda: store.delete(
            PERSON, collection=DELETE_COLLECTION, id=NEVER_WRITTEN_ID
        ),
        contains_after_delete=lambda: (DELETE_COLLECTION, WRITTEN_ID) in store._store,
    )


def test_V_DELETE_A_CONFORMING_VECTORS_WRITER_PASSES():
    """POSITIVE CONTROL."""
    embedder = _CountingEmbedder(should_fail=False)
    _run_vectors_delete(_VectorsStore(embedder), embedder)


def test_V_DELETE_THAT_DID_NOT_APPLY_IS_CAUGHT_BEFORE_CHECKING_PRESENCE():
    class RefusesDelete(_VectorsStore):
        def delete(self, initiator, *, collection, id):
            return MeshWriteResult.refused("pretend the delete is refused")

    embedder = _CountingEmbedder(should_fail=False)
    with pytest.raises(ConformanceFailure, match=r"vectors\.delete.*did not apply"):
        _run_vectors_delete(RefusesDelete(embedder), embedder)


def test_V_DELETE_THAT_REPORTS_WRITTEN_BUT_LEAVES_THE_OBJECT_IS_CAUGHT():
    """THE WRITE-SIDE LIE, REPLAYED ON THE DELETE PATH: `delete` reports `written` and the
    fixture's own store still holds the id afterward — never actually removed."""

    class DeleteIsANoOp(_VectorsStore):
        def delete(self, initiator, *, collection, id):
            initiator.require_person_or_delegate("vectors.delete")
            return MeshWriteResult.written()  # never actually deletes anything

    embedder = _CountingEmbedder(should_fail=False)
    with pytest.raises(ConformanceFailure, match=r"vectors\.delete.*STILL present"):
        _run_vectors_delete(DeleteIsANoOp(embedder), embedder)


def test_V_DELETE_OF_A_NEVER_WRITTEN_ID_THAT_REFUSES_IS_CAUGHT():
    """Deletion must be idempotent — a delete of an id that was never written must still report
    an applied state, the same reasoning `MeshGraphWriter.delete_edges` states for its own
    filter. A writer that refuses here is treating absence as an error."""

    class RefusesOnUnknownId(_VectorsStore):
        def delete(self, initiator, *, collection, id):
            initiator.require_person_or_delegate("vectors.delete")
            if (collection, id) not in self._store:
                return MeshWriteResult.refused(f"no such id: {id}")
            self._store.pop((collection, id), None)
            return MeshWriteResult.written()

    embedder = _CountingEmbedder(should_fail=False)
    with pytest.raises(ConformanceFailure, match=r"vectors\.delete.*never written.*not an applied"):
        _run_vectors_delete(RefusesOnUnknownId(embedder), embedder)


# ── check_graph_writer_write_node_contract, added 2026-10-01 — opens v0.9.6 scope, for Lane 1
# moving the ingest node off Neo4jIngestGraph ───────────────────────────────────────────────

NODE_LABEL = "Ingest"
NODE_ID = "ingest:2026-10-01-001"
FIRST_NODE_PAYLOAD = {"stage": "received"}
SECOND_NODE_PAYLOAD = {"stage": "extracting"}


def _run_write_node(store) -> None:
    check_graph_writer_write_node_contract(
        call_write_node=lambda: store.write_node(
            PERSON, label=NODE_LABEL, id=NODE_ID, payload=FIRST_NODE_PAYLOAD
        ),
        node_payload_after_write=lambda: store._nodes.get((NODE_LABEL, NODE_ID)),
        call_write_node_again_same_id_different_payload=lambda: store.write_node(
            PERSON, label=NODE_LABEL, id=NODE_ID, payload=SECOND_NODE_PAYLOAD
        ),
        node_payload_after_second_write=lambda: store._nodes.get((NODE_LABEL, NODE_ID)),
    )


def test_G_WRITE_NODE_A_CONFORMING_GRAPH_WRITER_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    _run_write_node(_EdgeStore())


def test_G_WRITE_NODE_THAT_DID_NOT_APPLY_IS_CAUGHT_BEFORE_CHECKING_THE_STORE():
    class RefusesWrite(_EdgeStore):
        def write_node(self, initiator, *, label, id, payload=None):
            return MeshWriteResult.refused("pretend the store is down")

    with pytest.raises(ConformanceFailure, match=r"graph\.write_node.*did not apply"):
        _run_write_node(RefusesWrite())


def test_G_WRITE_NODE_SECOND_WRITE_THAT_DID_NOT_APPLY_IS_CAUGHT():
    """The first write passes; the SECOND write is refused — caught by name, before the
    discriminate check that follows it is ever reached."""

    class RefusesSecondWrite(_EdgeStore):
        def __init__(self) -> None:
            super().__init__()
            self._writes = 0

        def write_node(self, initiator, *, label, id, payload=None):
            self._writes += 1
            if self._writes == 2:
                return MeshWriteResult.refused("pretend the second write is refused")
            return super().write_node(initiator, label=label, id=id, payload=payload)

    with pytest.raises(ConformanceFailure, match=r"graph\.write_node.*second write.*did not apply"):
        _run_write_node(RefusesSecondWrite())


def test_G_WRITE_NODE_THAT_STORES_NOTHING_IS_CAUGHT_BY_THE_FIXTURE_CHECK():
    """`written` reported twice, nothing ever persisted — both introspection reads come back
    `None`, caught by the discriminate check before either is read individually."""

    class Lost(_EdgeStore):
        def write_node(self, initiator, *, label, id, payload=None):
            initiator.require_person_or_delegate("graph.write_node")
            return MeshWriteResult.written()  # never actually stores anything

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run_write_node(Lost())


def test_G_WRITE_NODE_THAT_APPENDS_INSTEAD_OF_UPSERTING_IS_CAUGHT():
    """THE DEFECT THIS ARM EXISTS TO CATCH: a store that treats `write_node` like `write_edge` —
    the first write lands, the second is silently ignored (`setdefault`, never overwritten) —
    so a read after each write comes back identical, the same `(label, id)` frozen at its first
    payload forever. Caught by the discriminate check: two reads that must differ, didn't."""

    class AppendsInsteadOfUpserting(_EdgeStore):
        def write_node(self, initiator, *, label, id, payload=None):
            initiator.require_person_or_delegate("graph.write_node")
            self._nodes.setdefault((label, id), dict(payload or {}))
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match=r"fixture .* does not discriminate"):
        _run_write_node(AppendsInsteadOfUpserting())
