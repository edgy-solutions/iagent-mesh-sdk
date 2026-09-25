"""The ontology conformance arm must go red on the implementations it exists to reject.

THE DEFECT THE SHAPE PREVENTS: an ontology read that cannot tell *absent* from *could not ask*,
and a typed read that quietly stops being typed. Two of them shipped:

  * an existence check that fails or raises on an IRI that does not exist — the caller reads
    "could not ask" as a legitimate no, or (the inverse) a check that answers yes to everything,
    so a decision-record write is guarded by a check that cannot fail;
  * the SELECT executor, which drops term types — ``"42"^^xsd:integer`` comes back as ``"42"``
    and every downstream comparison silently changes meaning.

A conformance arm is only worth its green if each of those implementations makes it RED, and red
for ITS OWN reason — so every broken variant below is matched on the message that names the
defect, not merely on the exception type. The conforming reference fake is the positive control:
an arm that raised on everything would pass every test that only asserts a raise.

Nothing here imports a driver; the store is a dict.
"""
from __future__ import annotations

import re
from typing import Optional

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_offline,
    check_ontology_contract,
)
from iagent_mesh.interfaces import Initiator, MeshOntology
from iagent_mesh.results import MeshResult

PERSON = Initiator(subject="alice", kind="person")
PRESENT = "ex:present"
ABSENT = "ex:absent"
INT_TERM = '"42"^^xsd:integer'
LANG_TERM = '"hello"@en'
TYPED = (INT_TERM, LANG_TERM)


# ── the reference implementation ─────────────────────────────────────────────────────────

class _Ontology:
    """A conforming in-memory ontology. Broken variants below override ONE method each."""

    MODES: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._store = {PRESENT: [f"ex:count {INT_TERM}", f"ex:label {LANG_TERM}"]}

    def ask(self, initiator: Initiator, *, iri: str, graph: Optional[str] = None) -> MeshResult:
        initiator.require_person("ask")
        if iri in self._store:
            return MeshResult.answered([iri])
        return MeshResult.empty()

    def construct(
        self, initiator: Initiator, *, subject: str, graph: Optional[str] = None
    ) -> MeshResult:
        initiator.require_person("construct")
        if subject not in self._store:
            return MeshResult.empty()
        body = " ;\n    ".join(self._store[subject])
        return MeshResult.answered([f"{subject}\n    {body} ."])


def _run(impl, *, typed_terms=TYPED) -> None:
    check_ontology_contract(
        impl,
        call_ask_present=lambda: impl.ask(PERSON, iri=PRESENT),
        call_ask_absent=lambda: impl.ask(PERSON, iri=ABSENT),
        call_construct=lambda: impl.construct(PERSON, subject=PRESENT),
        typed_terms=typed_terms,
    )


# ── the positive control ─────────────────────────────────────────────────────────────────

def test_A_CONFORMING_ONTOLOGY_PASSES_EVERY_ARM():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    impl = _Ontology()
    assert isinstance(impl, MeshOntology)
    _run(impl)
    check_offline(
        impl,
        operations=[
            ("ask", lambda i: impl.ask(i, iri=PRESENT)),
            ("construct", lambda i: impl.construct(i, subject=PRESENT)),
        ],
    )


def test_EACH_KIND_OF_TYPED_TERM_IS_ENOUGH_ON_ITS_OWN():
    """A datatype-only and a language-only fixture are each legal; a suite that demanded both
    would refuse a store that simply holds one kind of term."""
    _run(_Ontology(), typed_terms=(INT_TERM,))
    _run(_Ontology(), typed_terms=(LANG_TERM,))


# ── ask: absence is an answer ────────────────────────────────────────────────────────────

def test_AN_ASK_THAT_FAILS_ON_AN_ABSENT_IRI_IS_REFUSED():
    """`failed` on an IRI that does not exist is 'could not ask' read from a legitimate absence.
    The caller cannot tell the store being down from the record not being there."""

    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            if iri == ABSENT:
                return MeshResult.failed("no such iri")
            return super().ask(initiator, iri=iri, graph=graph)

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask.*could not ask"):
        _run(Broken())


def test_AN_ASK_THAT_REPORTS_UNREACHABLE_ON_AN_ABSENT_IRI_IS_REFUSED():
    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            if iri == ABSENT:
                return MeshResult.unreachable("not there")
            return super().ask(initiator, iri=iri, graph=graph)

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask.*'unreachable'.*could not ask"):
        _run(Broken())


def test_AN_ASK_THAT_RAISES_ON_AN_ABSENT_IRI_IS_REFUSED_AS_A_CONFORMANCE_FAILURE():
    """A raise is the loudest way to say 'could not ask', and it must surface as the arm's own
    failure naming the operation, not as a bare KeyError from inside the implementer's store."""

    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            if iri == ABSENT:
                raise KeyError(iri)
            return super().ask(initiator, iri=iri, graph=graph)

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask.*raised KeyError.*could not ask"):
        _run(Broken())


def test_AN_ASK_THAT_ANSWERS_YES_TO_EVERYTHING_CANNOT_TELL_THE_FIXTURE_APART():
    """A check that cannot say no. Present and absent both present as 'answered', so the arm
    refuses on the FIXTURE before it ever reads an outcome — it would otherwise pass the
    present arm and be judged on the absent one only."""

    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            return MeshResult.answered([iri])

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask present vs absent.*does not discriminate"):
        _run(Broken())


def test_AN_ASK_THAT_IS_ALWAYS_EMPTY_CANNOT_TELL_THE_FIXTURE_APART():
    """The mirror: an always-empty ask passes an absent-only suite trivially. Present and absent
    both present as 'empty', so the fixture pair is refused as non-discriminating."""

    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask present vs absent.*does not discriminate"):
        _run(Broken())


def test_AN_ASK_THAT_REPORTS_AN_ABSENT_IRI_AS_EXISTING_IS_REFUSED():
    """An IRI that does not exist reported as existing. Reachable only when the two outcomes
    differ (here, inverted) — otherwise the fixture check fires first."""

    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            if iri == ABSENT:
                return MeshResult.answered([iri])
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask.*reported as existing"):
        _run(Broken())


def test_AN_ASK_THAT_FAILS_ON_A_PRESENT_IRI_FAILS_THE_POSITIVE_CONTROL():
    """The absent arm is satisfied (`empty`), so only the positive control can catch an ask()
    that never manages to answer yes."""

    class Broken(_Ontology):
        def ask(self, initiator, *, iri, graph=None):
            if iri == PRESENT:
                return MeshResult.failed("store down")
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"ontology\.ask.*positive control"):
        _run(Broken())


# ── construct: types intact ──────────────────────────────────────────────────────────────

def test_A_CONSTRUCT_THAT_STRIPS_TERM_TYPES_IS_REFUSED_NAMING_THE_TERM():
    """THE SELECT-EXECUTOR DEFECT. `"42"^^xsd:integer` comes back as `"42"`: still well-formed,
    still plausible, and a different value to every consumer that compares or sorts."""

    class Broken(_Ontology):
        def construct(self, initiator, *, subject, graph=None):
            initiator.require_person("construct")
            return MeshResult.answered(['ex:present ex:count "42" ; ex:label "hello" .'])

    with pytest.raises(ConformanceFailure, match=r"ontology\.construct.*" + re.escape(INT_TERM) + r".*DROPPED"):
        _run(Broken())


def test_A_CONSTRUCT_THAT_DROPS_ONLY_THE_LANGUAGE_TAG_IS_REFUSED():
    """Each term is checked on its own: keeping the datatype must not excuse losing the tag."""

    class Broken(_Ontology):
        def construct(self, initiator, *, subject, graph=None):
            initiator.require_person("construct")
            return MeshResult.answered([f'ex:present ex:count {INT_TERM} ; ex:label "hello" .'])

    with pytest.raises(ConformanceFailure, match=re.escape(LANG_TERM) + r".*DROPPED"):
        _run(Broken())


def test_A_CONSTRUCT_RETURNING_BINDING_ROWS_INSTEAD_OF_TURTLE_TEXT_IS_REFUSED():
    """Rows that are tuples/dicts are the SELECT executor's bindings — where types are lost."""

    class Broken(_Ontology):
        def construct(self, initiator, *, subject, graph=None):
            initiator.require_person("construct")
            return MeshResult.answered([("ex:present", "ex:count", "42")])

    with pytest.raises(ConformanceFailure, match=r"ontology\.construct.*not str"):
        _run(Broken())


def test_A_CONSTRUCT_THAT_ANSWERS_WITH_BLANK_TEXT_IS_REFUSED():
    class Broken(_Ontology):
        def construct(self, initiator, *, subject, graph=None):
            initiator.require_person("construct")
            return MeshResult.answered(["  "])

    with pytest.raises(ConformanceFailure, match=r"ontology\.construct.*blank"):
        _run(Broken())


def test_A_CONSTRUCT_THAT_FINDS_NOTHING_FOR_A_PRESENT_SUBJECT_IS_REFUSED():
    """`empty` for a subject `ask` says exists: nothing to compare types against, and a typed
    read that returns nothing is not a typed read."""

    class Broken(_Ontology):
        def construct(self, initiator, *, subject, graph=None):
            initiator.require_person("construct")
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"ontology\.construct.*PRESENT subject.*'empty'"):
        _run(Broken())


# ── the fixture must discriminate ────────────────────────────────────────────────────────

def test_AN_EMPTY_TYPED_TERM_LIST_IS_REFUSED():
    """A suite over nothing passes everything — including a construct that strips every type."""
    with pytest.raises(ConformanceFailure, match=r"ontology\.construct.*no typed terms"):
        _run(_Ontology(), typed_terms=())


def test_PLAIN_STRING_TERMS_ARE_REFUSED_AS_NON_DISCRIMINATING():
    """`"42"` is its own stripped form, so it cannot tell a typed read from an untyped one — a
    type-stripping construct would pass it. Refused even against the CONFORMING implementation,
    because the defect is in the fixture."""
    with pytest.raises(ConformanceFailure, match=r"fixture does not discriminate.*carries no datatype"):
        _run(_Ontology(), typed_terms=('"42"',))


def test_ONE_PLAIN_TERM_AMONG_TYPED_ONES_IS_STILL_REFUSED():
    with pytest.raises(ConformanceFailure, match=r"fixture does not discriminate"):
        _run(_Ontology(), typed_terms=(INT_TERM, '"plain"'))
