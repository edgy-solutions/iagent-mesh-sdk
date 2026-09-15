"""The Protocols and their conformance suite, exercised by a DELIBERATELY BROKEN implementation.

A conformance suite is only worth its green if it goes red on the implementations it exists to
reject. So most arms here build an implementation that violates exactly one property and assert
the suite catches THAT one — a suite that raised on everything would pass a test asserting only
that it raises.

Nothing here imports a driver, and nothing constructs a real substrate: the offline arm is the
half that must always run, and this file is its own demonstration that it can.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    assert_fixture_discriminates,
    check_live,
    check_offline,
)
from iagent_mesh.interfaces import (
    Initiator,
    MeshGraph,
    MeshOntology,
    MeshVectors,
    ServiceIdentityRefused,
)
from iagent_mesh.results import MeshResult

PERSON = Initiator(subject="alice", kind="person")


# ── the initiator ────────────────────────────────────────────────────────────────────────

def test_a_service_identity_is_refused_and_the_raise_names_the_operation():
    svc = Initiator(subject="svc:anything", kind="service")
    with pytest.raises(ServiceIdentityRefused, match="registry"):
        svc.require_person("registry")


def test_a_person_passes_through_unchanged():
    """POSITIVE CONTROL. A check that refused everything would satisfy the arm above."""
    assert PERSON.require_person("registry") is PERSON


def test_kind_is_DECLARED_not_sniffed_from_the_subject():
    """The rule is 'refuse a service identity'; the obvious implementation is to look for a
    `svc:` prefix, and it would violate the older rule that identity is carried OPAQUE.

    A subject that LOOKS like a service is a person if the token said so — because subject
    spellings differ per deployment and a parser that works in sandbox mislabels at work,
    silently, since both readings produce a plausible identity.
    """
    looks_like_a_service = Initiator(subject="service-account-iagent-review-starter", kind="person")
    assert looks_like_a_service.require_person("registry") is looks_like_a_service

    looks_like_a_person = Initiator(subject="alice@example.com", kind="service")
    with pytest.raises(ServiceIdentityRefused):
        looks_like_a_person.require_person("registry")


def test_an_empty_subject_is_refused():
    with pytest.raises(Exception, match="empty|anonymous"):
        Initiator(subject="   ", kind="person")


# ── the fixture rule ─────────────────────────────────────────────────────────────────────

def test_assert_fixture_discriminates_REFUSES_an_undiscriminating_pair():
    """The rule, not the instance. Both of this suite's authors shipped a fixture that could not
    tell the fix from the defect."""
    with pytest.raises(ConformanceFailure, match="does not discriminate"):
        assert_fixture_discriminates("two empties", MeshResult.empty(), MeshResult.empty(),
                                     describe=lambda r: r.outcome)


def test_assert_fixture_discriminates_PASSES_a_real_pair():
    assert_fixture_discriminates("two empties", MeshResult.empty(),
                                 MeshResult.unreachable("no route"), describe=lambda r: r.outcome)


# ── the offline arm, driven by implementations broken one way at a time ──────────────────

def _ok(initiator: Initiator) -> MeshResult:
    initiator.require_person("op")
    return MeshResult.answered([1])


def test_a_conforming_operation_passes():
    """POSITIVE CONTROL for every rejection below."""
    check_offline(object(), operations=[("op", _ok)])


def test_an_operation_that_accepts_a_SERVICE_identity_is_caught():
    check = lambda i: MeshResult.answered([1])  # noqa: E731 — never checks the initiator
    with pytest.raises(ConformanceFailure, match="SERVICE identity"):
        check_offline(object(), operations=[("op", check)])


def test_an_operation_returning_a_BARE_LIST_is_caught():
    def bare(i: Initiator):
        i.require_person("op")
        return [1, 2]
    with pytest.raises(ConformanceFailure, match="not MeshResult"):
        check_offline(object(), operations=[("op", bare)])


def test_an_UNDECLARED_mode_is_caught():
    def odd(i: Initiator) -> MeshResult:
        i.require_person("op")
        return MeshResult.answered([1], mode="sparse")
    with pytest.raises(ConformanceFailure, match="does not declare"):
        check_offline(object(), operations=[("op", odd)], declared_modes=("hybrid", "bm25"))


def test_a_DECLARED_mode_passes():
    def fine(i: Initiator) -> MeshResult:
        i.require_person("op")
        return MeshResult.answered([1], mode="bm25")
    check_offline(object(), operations=[("op", fine)], declared_modes=("hybrid", "bm25"))


def test_an_EMPTY_operation_list_is_refused():
    """The likeliest way to satisfy conformance without conforming: hand it nothing."""
    with pytest.raises(ConformanceFailure, match="zero operations"):
        check_offline(object(), operations=[])


def test_a_MISSING_operation_is_caught_as_missing_rather_than_as_a_refusal():
    def absent(i: Initiator) -> MeshResult:
        raise NotImplementedError
    with pytest.raises(ConformanceFailure, match="not implemented"):
        check_offline(object(), operations=[("op", absent)])


# ── the live arm ─────────────────────────────────────────────────────────────────────────

def test_the_live_arm_catches_a_failure_reported_as_an_empty():
    """The confident-zero defect, which is what the whole arc is for."""
    with pytest.raises(ConformanceFailure, match="does not discriminate"):
        check_live(object(), operation="read",
                   call_reachable_empty=MeshResult.empty,
                   call_unreachable=MeshResult.empty,
                   read_provenance=lambda: ["urn:x"])


def test_the_live_arm_REFUSES_TO_SKIP_the_provenance_check():
    """The one property that cannot be checked offline. A live arm that omits it has verified
    the half that was already provable."""
    with pytest.raises(ConformanceFailure, match="no provenance reader"):
        check_live(object(), operation="read",
                   call_reachable_empty=MeshResult.empty,
                   call_unreachable=lambda: MeshResult.unreachable("no route"),
                   read_provenance=None)


def test_the_live_arm_catches_a_read_that_recorded_NOTHING():
    with pytest.raises(ConformanceFailure, match="recorded no provenance"):
        check_live(object(), operation="read",
                   call_reachable_empty=MeshResult.empty,
                   call_unreachable=lambda: MeshResult.unreachable("no route"),
                   read_provenance=lambda: [])


def test_a_conforming_live_run_passes():
    """POSITIVE CONTROL for the three live rejections."""
    check_live(object(), operation="read",
               call_reachable_empty=MeshResult.empty,
               call_unreachable=lambda: MeshResult.unreachable("no route"),
               read_provenance=lambda: ["urn:dataset:x"])


# ── the interfaces themselves ────────────────────────────────────────────────────────────

def test_the_read_only_interfaces_declare_NO_write_operation():
    """MeshGraph has no write half because there is no caller; MeshOntology has none because
    there is no verified working path. Both are rulings, so a later 'for symmetry' addition
    should have to argue with a test rather than with a comment."""
    for proto in (MeshGraph, MeshOntology, MeshVectors):
        names = [n for n in dir(proto) if not n.startswith("_")]
        offenders = [n for n in names
                     if any(w in n for w in ("write", "insert", "update", "delete", "upsert"))]
        assert not offenders, f"{proto.__name__} declares write-shaped operations {offenders}"


def test_mode_vocabularies_are_declared_per_interface():
    """Not centrally — a closed enum in the SDK would make every new mode an SDK release."""
    assert MeshVectors.MODES == ("hybrid", "bm25")
    # A read with one way to answer declares an EMPTY vocabulary rather than omitting the
    # attribute, so a consumer can tell "no mode here" from "the implementation forgot".
    assert MeshGraph.MODES == () and MeshOntology.MODES == ()


def test_the_sdk_imports_no_driver_and_no_implementation():
    """R-038 one level up, asserted rather than claimed: interfaces that imported their
    implementation would make the dependency real however the module is named."""
    import ast
    import pathlib

    for mod in ("interfaces.py", "conformance.py", "results.py"):
        src = pathlib.Path(__file__).resolve().parents[1] / "iagent_mesh" / mod
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
                imported.update(a.name for a in node.names)
        banned = {"neo4j", "weaviate", "rdflib", "SPARQLWrapper", "langfuse", "httpx", "urllib"}
        hits = {m for m in imported for b in banned if m == b or m.startswith(b + ".")}
        assert not hits, f"{mod} imports {sorted(hits)} — the SDK owns interfaces only"
