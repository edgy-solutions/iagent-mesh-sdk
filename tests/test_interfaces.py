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


def test_nominate_scopes_by_a_SEQUENCE_of_domains_not_a_single_one():
    """A REGRESSION GUARD, because the singular reads as the simpler design and is the form that
    was superseded (2026-06-28).

    Both live call sites scope by a list. Reverting to a single string would force loop-and-merge
    at the caller, and that is a RANKING change rather than an ergonomic one: three searches
    return three separately-ranked lists whose scores are not comparable across calls, so the
    caller has no basis on which to interleave them. It is also N× the embedding cost for one
    phrase, and it makes ADR-0009's `domains == []` clause inexpressible.
    """
    import inspect

    sig = inspect.signature(MeshVectors.nominate)
    assert "domains" in sig.parameters, "nominate must scope by a sequence of domains"
    assert "domain" not in sig.parameters, (
        "the singular `domain` was superseded; keeping it invites the loop-and-merge workaround"
    )
    assert sig.parameters["domains"].default == (), "an empty sequence means no domain filter"


# ── the marker collection: a carrier that is OURS BY CONSTRUCTION ────────────────────────

from iagent_mesh.conformance import check_embedding_contract, check_writer_marker  # noqa: E402
from iagent_mesh.interfaces import (  # noqa: E402
    MESH_COLLECTION_META,
    CorruptCollectionMarker,
    collection_marker,
    marker_is_stale,
    read_collection_marker,
)

_WRITTEN = dict(collection="OntologyClass", model="nomic-embed-text", version="1.5",
                dimension=768, written_by="doc-tools-sync",
                collection_created_unix_ms=1_780_980_389_974)
_MARKER = collection_marker(**_WRITTEN)
_FRESH = lambda: 1_780_980_389_974          # noqa: E731 — oldest object, same age as the marker
_OK = dict(operation="nominate", declared_model="nomic-embed-text", declared_version="1.5",
           expected_dimension=768, read_stored_dimension=lambda: 768,
           read_oldest_object_unix_ms=_FRESH)


def test_A_MATCHING_MARKER_OPENS():
    """POSITIVE CONTROL for every refusal below."""
    check_embedding_contract(**_OK, read_marker=lambda: _MARKER)


def test_a_different_MODEL_refuses_at_open_naming_both():
    other = collection_marker(**{**_WRITTEN, "model": "other-model"})
    with pytest.raises(ConformanceFailure) as exc:
        check_embedding_contract(**_OK, read_marker=lambda: other)
    assert "other-model" in str(exc.value) and "nomic-embed-text" in str(exc.value)


def test_a_different_VERSION_refuses_too():
    """A re-trained model spells the same and produces incompatible vectors."""
    with pytest.raises(ConformanceFailure, match="2.0"):
        check_embedding_contract(**_OK,
                                 read_marker=lambda: collection_marker(**{**_WRITTEN, "version": "2.0"}))


def test_ABSENT_opens_and_reports_the_gap():
    reported = []
    check_embedding_contract(**_OK, read_marker=lambda: None, report_gap=reported.append)
    assert len(reported) == 1 and MESH_COLLECTION_META in reported[0]


def test_ABSENT_with_no_reporter_is_a_FAILURE():
    with pytest.raises(ConformanceFailure, match="ABSENT IS NOT MATCHING"):
        check_embedding_contract(**_OK, read_marker=lambda: None)


def test_a_MALFORMED_marker_REFUSES_rather_than_reading_as_absent():
    """Nobody-wrote-one is a gap; something-wrote-OURS-badly is a failure."""
    with pytest.raises(ConformanceFailure, match="not readable|damaged"):
        check_embedding_contract(**_OK, read_marker=lambda: {"collection": "OntologyClass"},
                                 report_gap=lambda _m: None)


# ── staleness: the objection that rejected this carrier, and the seal that answers it ─────

def test_A_MARKER_THAT_OUTLIVED_ITS_COLLECTION_READS_AS_ABSENT():
    """THE ARM THIS CARRIER EXISTS TO SURVIVE. A description died with what it described; a
    marker in its own collection does not, so a recreated-and-re-ingested collection would
    otherwise carry a confident statement about vectors that no longer exist.

    It reads as ABSENT rather than MISMATCH: refusing on a stale marker would take a healthy
    collection down, and trusting it is the confident-stale reading itself.
    """
    reported = []
    check_embedding_contract(**{**_OK, "read_oldest_object_unix_ms": lambda: 1_790_000_000_000},
                             read_marker=lambda: _MARKER, report_gap=reported.append)
    assert len(reported) == 1 and "predates" in reported[0]


def test_AN_EMPTY_COLLECTION_CANNOT_BE_DATED_and_that_is_ABSENT_not_valid():
    """No object means no proxy for the collection's age. Treating an undatable marker as
    current is exactly the reading the staleness field exists to prevent."""
    reported = []
    check_embedding_contract(**{**_OK, "read_oldest_object_unix_ms": lambda: None},
                             read_marker=lambda: _MARKER, report_gap=reported.append)
    assert len(reported) == 1


def test_marker_is_stale_DISCRIMINATES_rather_than_always_answering_one_way():
    """FIXTURE DISCRIMINATION, on the staleness helper itself: a check that answered the same
    for a fresh and a recreated collection would pass both arms above for the wrong reason."""
    m = read_collection_marker(_MARKER)
    assert marker_is_stale(m, 1_790_000_000_000) is not marker_is_stale(m, _FRESH())


# ── the writer: one implementation, admission checks its output ──────────────────────────

def test_a_conforming_writer_is_admitted_and_the_round_trip_holds():
    """The property kept from the previous carrier because it is what made that one safe and it
    is carrier-independent: ONE implementation of the write, admission checking the output."""
    check_writer_marker(**_WRITTEN)


def test_a_writer_that_loses_a_field_fails_admission():
    with pytest.raises(Exception):
        check_writer_marker(**{**_WRITTEN, "written_by": "  "})


def test_every_field_is_required_because_a_partial_marker_cannot_discriminate():
    with pytest.raises(Exception, match="needs every field|discriminate"):
        collection_marker(**{**_WRITTEN, "model": ""})


def test_THE_STALENESS_PROXY_IS_DECLARED_DEFEATED_not_quietly_shipped():
    """A KNOWN-BROKEN CHECK THAT SAYS SO IS A GAP WITH AN OWNER; the same check shipped silent is
    the confident green this whole mechanism exists to end.

    Measured 2026-09-15 by the eo lane: the writer replaces objects on deterministic UUIDs and the
    store preserves `creationTimeUnix`, so the oldest object's creation time does not move while
    the vectors are rewritten. This asserts the WARNING is present, so the defect cannot be
    silently inherited by a reader who trusts the docstring — and it fails if someone deletes the
    warning without fixing the proxy.
    """
    import iagent_mesh.interfaces as I

    doc = I.marker_is_stale.__doc__ or ""
    assert "ALREADY DEFEATED" in doc, "the proxy's known defeat must be stated where it is used"
    assert "UNPROVEN" in doc, "a non-stale verdict must be declared as unproven, not as freshness"
