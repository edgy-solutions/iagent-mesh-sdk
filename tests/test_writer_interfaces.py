"""The write half's own boundary: `require_person_or_delegate`, `Embedder`, and the three sibling
write Protocols — exercised the same way `test_interfaces.py` exercises the read half, with a
deliberately broken implementation proving each arm bites.

RULED 2026-09-27: sibling Protocols, never new methods on the read interfaces (asserted here by
re-checking the read Protocols stay untouched); a wider allowlist at the write boundary than the
read boundary's `require_person` (person-only); `written_without_vector` opt-in only.
"""
from __future__ import annotations

import pytest

from iagent_mesh.interfaces import (
    DelegateIdentityRefused,
    EdgeIdentity,
    Embedder,
    Initiator,
    MeshGraph,
    MeshGraphWriter,
    MeshOntology,
    MeshOntologyWriter,
    MeshVectors,
    MeshVectorsWriter,
    ServiceIdentityRefused,
)
from iagent_mesh.write_results import MeshWriteResult

PERSON = Initiator(subject="alice", kind="person")
DELEGATE = Initiator(subject="lane:ca", kind="delegate", on_behalf_of="chris")
SERVICE = Initiator(subject="svc:anything", kind="service")


# ── the write boundary: a WIDER allowlist than require_person ────────────────────────────

def test_a_service_identity_is_refused_and_the_raise_names_the_operation():
    with pytest.raises(ServiceIdentityRefused, match="ontology.upsert"):
        SERVICE.require_person_or_delegate("ontology.upsert")


def test_a_person_passes_through_unchanged():
    """POSITIVE CONTROL. A check that refused everything would satisfy the arm above."""
    assert PERSON.require_person_or_delegate("op") is PERSON


def test_a_DELEGATE_is_ADMITTED_here_unlike_at_the_read_boundary():
    """THE PROPERTY THIS METHOD EXISTS TO ADD. `require_person` refuses a delegate;
    `require_person_or_delegate` — the write boundary, ruled 2026-09-27 — admits it. A shared
    fixture proves the two gates actually differ rather than one being a copy of the other."""
    assert DELEGATE.require_person_or_delegate("op") is DELEGATE
    with pytest.raises(DelegateIdentityRefused):
        DELEGATE.require_person("op")


def test_a_service_is_refused_the_SAME_way_at_both_boundaries():
    """A service is refused by BOTH gates, and by the SAME exception — the write boundary is
    wider by one kind, not a differently-shaped gate."""
    with pytest.raises(ServiceIdentityRefused):
        SERVICE.require_person("op")
    with pytest.raises(ServiceIdentityRefused):
        SERVICE.require_person_or_delegate("op")


def test_no_new_exception_for_a_delegate_at_the_write_boundary():
    """A delegate never reaches the branch that would raise DelegateIdentityRefused here — there
    is nothing left for it to be refused FOR. That exception stays scoped to require_person."""
    try:
        DELEGATE.require_person_or_delegate("op")
    except DelegateIdentityRefused:
        pytest.fail("require_person_or_delegate must never raise DelegateIdentityRefused")


# ── the read interfaces stay untouched ────────────────────────────────────────────────────

def test_the_read_interfaces_gained_NO_new_method():
    """Ruled: sibling Protocols, never new methods on the read interfaces. Pinning the exact
    method sets so a write method added here-by-mistake is caught by name, not by a vaguer
    'still read-only' shape check."""
    assert {n for n in dir(MeshGraph) if not n.startswith("_") and n != "MODES"} == {
        "registry", "providers_for", "classes_with_a_verb", "data_assets_for",
        "edge", "path", "operable_subjects", "verbs_for", "ancestors",
    }
    assert {n for n in dir(MeshOntology) if not n.startswith("_") and n != "MODES"} == {"ask", "construct"}
    assert {n for n in dir(MeshVectors) if not n.startswith("_") and n != "MODES"} == {
        "embedding_model", "nominate", "collection_present",
    }


# ── the writer protocols exist with the ruled shape ───────────────────────────────────────

def test_MeshGraphWriter_declares_write_and_delete_as_the_write_half():
    """AMENDED 2026-09-29, on the worker's own packet back: `delete_edges` joined `write_edge` as
    part of the write half, not a later addition — three of the registrar's four graph paths
    delete, and the writer and the cleanup must agree on identity. AMENDED AGAIN 2026-09-30, on
    the promotion adapter's own rejection packet back: `has_edges` joined as the existence check
    that adapter named as missing."""
    assert {n for n in dir(MeshGraphWriter) if not n.startswith("_")} == {
        "write_edge", "delete_edges", "has_edges",
    }


def test_MeshOntologyWriter_requires_graph_not_optional():
    """The asymmetry with MeshOntology.ask's optional `graph` is deliberate: a write choosing
    'anywhere' is the unscoped default-graph insert this Protocol exists to make unrepresentable."""
    import inspect

    sig = inspect.signature(MeshOntologyWriter.upsert)
    assert sig.parameters["graph"].default is inspect.Parameter.empty, (
        "graph must be REQUIRED on the writer — an optional graph reopens the unscoped-write path"
    )


def test_MeshVectorsWriter_declares_write_and_relocate_as_SEPARATE_methods():
    """The hazard ruled against 2026-09-27: one method taking an optional vector would make
    'supply your own vector' look like a normal parameter on the everyday write path. AMENDED
    2026-09-30, on the promotion adapter's own rejection packet back: `delete` joined as genuinely
    new capability — unlike the graph writer's two needs, nothing here answered it beforehand."""
    names = {n for n in dir(MeshVectorsWriter) if not n.startswith("_")}
    assert names == {"write", "relocate", "delete"}


def test_write_defaults_vector_required_to_True():
    import inspect

    sig = inspect.signature(MeshVectorsWriter.write)
    assert sig.parameters["vector_required"].default is True


def test_relocate_takes_a_vector_and_NOT_text():
    """Relocation is not a shortcut for `write` — it must not be embeddable-from-text."""
    import inspect

    sig = inspect.signature(MeshVectorsWriter.relocate)
    assert "vector" in sig.parameters
    assert "text" not in sig.parameters


def test_Embedder_declares_embed_and_identity():
    assert {n for n in dir(Embedder) if not n.startswith("_")} == {"embed", "identity"}


# ── conformance: check_writer_offline must bite ───────────────────────────────────────────

from iagent_mesh.conformance import ConformanceFailure, check_writer_offline  # noqa: E402


_IDENTITY = EdgeIdentity(subject="s", verb="v", object="o", key="k")


class _ConformingGraphWriter:
    def write_edge(self, initiator: Initiator, *, identity: EdgeIdentity, payload=None) -> MeshWriteResult:
        initiator.require_person_or_delegate("graph.write_edge")
        return MeshWriteResult.written()


def _run_offline(writer) -> None:
    check_writer_offline(
        writer,
        operations=[("write_edge", lambda i: writer.write_edge(i, identity=_IDENTITY))],
    )


def test_A_CONFORMING_WRITER_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    _run_offline(_ConformingGraphWriter())


def test_A_WRITER_THAT_ACCEPTS_A_SERVICE_IDENTITY_IS_CAUGHT():
    class Broken(_ConformingGraphWriter):
        def write_edge(self, initiator, *, identity, payload=None):
            return MeshWriteResult.written()  # no identity gate at all

    with pytest.raises(ConformanceFailure, match="accepted a SERVICE identity"):
        _run_offline(Broken())


def test_A_WRITER_THAT_REFUSES_A_DELEGATE_IS_CAUGHT():
    """THE ARM ONLY THE WRITE SIDE NEEDS. `check_offline` (the read arm) never has to test this,
    because reads keep the narrower person-only gate. A writer that reused `require_person`
    instead of `require_person_or_delegate` would refuse the exact identity ruling item 4 admits,
    and this is the arm that catches that mistake."""
    class Broken(_ConformingGraphWriter):
        def write_edge(self, initiator, *, identity, payload=None):
            initiator.require_person("graph.write_edge")  # the READ gate, wrong one for a write
            return MeshWriteResult.written()

    with pytest.raises(ConformanceFailure, match="refused a DELEGATE identity"):
        _run_offline(Broken())


def test_A_WRITER_RETURNING_A_BARE_BOOL_IS_CAUGHT():
    class Broken(_ConformingGraphWriter):
        def write_edge(self, initiator, *, identity, payload=None):
            initiator.require_person_or_delegate("graph.write_edge")
            return True  # not a MeshWriteResult

    with pytest.raises(ConformanceFailure, match="not MeshWriteResult"):
        _run_offline(Broken())


def test_AN_EMPTY_operation_list_IS_REFUSED():
    with pytest.raises(ConformanceFailure, match="no operations supplied"):
        check_writer_offline(_ConformingGraphWriter(), operations=[])
