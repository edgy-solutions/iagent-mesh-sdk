"""The conformance suite: what makes a Protocol a CONTRACT rather than a type hint.

An implementation is admitted by PASSING THIS, never by being named in the SDK. It runs in the
implementer's own CI, pinned to the SDK minor — so the contract cannot drift silently under an
implementer: the suite moves with the SDK and their build goes red.

── TWO ARMS, AND THE SPLIT IS NOT A CONVENIENCE ────────────────────────────────────────────
``check_offline`` needs no substrate and MUST ALWAYS RUN. ``check_live`` needs a real one,
because **provenance-recorded cannot be faked**: asserting that an implementation *would* record
what it read is asserting nothing. An offline-only suite admits an implementation that records
nothing, which is one of the three properties the whole arc exists to guarantee.

── THE FIXTURE RULE, WHICH IS THE ONE THAT BITES ───────────────────────────────────────────
**A fixture is a legal input that happens to make two behaviours identical.** An alphabetical
order fixture cannot tell sorted from preserved; an empty-store fixture cannot tell
answered-nothing from failed-silently. So this suite ASSERTS ITS OWN FIXTURES DISCRIMINATE
before trusting them — :func:`assert_fixture_discriminates` — rather than carrying a list of
remembered instances. A suite whose fixtures are undiscriminating passes exactly the
error-swallowing implementations it exists to reject.

The ontology arm, :func:`check_ontology_contract`, takes the implementer's OWN fixture (an
absent IRI, a present one, and the typed terms their serializer emits), because only they know
their store; it asserts that fixture discriminates before trusting it.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Optional, Sequence

from .interfaces import (
    MESH_COLLECTION_META,
    CorruptCollectionMarker,
    DelegateIdentityRefused,
    Initiator,
    ServiceIdentityRefused,
    collection_marker,
    marker_predates_collection,
    read_collection_marker,
)
from .results import MeshResult
from .write_results import MeshWriteResult

__all__ = [
    "check_embedding_contract",
    "check_writer_marker",
    "ConformanceFailure",
    "assert_fixture_discriminates",
    "check_offline",
    "check_live",
    "check_ontology_contract",
    "check_writer_offline",
    "check_ontology_writer_contract",
    "check_graph_writer_contract",
    "check_vectors_writer_contract",
    "check_graph_writer_has_edges_contract",
    "check_graph_writer_key_only_delete_contract",
    "check_vectors_writer_delete_contract",
    "check_graph_writer_write_node_contract",
    "check_graph_writer_has_node_contract",
    "check_graph_writer_delete_node_contract",
]


class ConformanceFailure(AssertionError):
    """An implementation does not satisfy the contract. Always names the operation."""


def _fail(operation: str, why: str) -> None:
    raise ConformanceFailure(f"{operation}: {why}")


def assert_fixture_discriminates(
    label: str, a: Any, b: Any, *, describe: Callable[[Any], Any] = lambda x: x
) -> None:
    """Refuse a fixture pair that cannot tell the fix from the defect.

    Called BEFORE the arm that uses the pair, so an undiscriminating fixture is a loud failure
    rather than a silent pass. This exists because both of its authors shipped one: an order
    fixture that was already alphabetical, and an empty-store fixture that could not separate a
    failure from a legitimate empty.
    """
    if describe(a) == describe(b):
        raise ConformanceFailure(
            f"fixture {label!r} does not discriminate: both cases present as "
            f"{describe(a)!r}, so this arm would pass against the defect it tests for"
        )


# ── the offline arm ──────────────────────────────────────────────────────────────────────


def check_offline(
    impl: Any,
    *,
    operations: Sequence[tuple[str, Callable[[Initiator], MeshResult]]],
    declared_modes: Sequence[str] = (),
) -> None:
    """Properties provable with no substrate. ALWAYS RUN THIS.

    ``operations`` is a list of ``(name, call)`` pairs where ``call`` takes an initiator and
    invokes one operation — the implementer supplies them because only they know the arguments
    their operations need.
    """
    if not operations:
        # A SUITE OVER NOTHING PASSES EVERYTHING. The likeliest way an implementer satisfies
        # conformance without conforming is to hand it an empty list.
        _fail("check_offline", "no operations supplied — a conformance run over zero operations "
                              "is a green that proves nothing")

    person = Initiator(subject="conformance-person", kind="person")
    service = Initiator(subject="conformance-service", kind="service")

    # THE FIXTURE MUST DISCRIMINATE: if both initiators presented identically there would be
    # nothing for the refusal arm to detect.
    assert_fixture_discriminates("initiator kinds", person, service, describe=lambda i: i.kind)

    for name, call in operations:
        # ── identity is an argument, and a service identity is refused at the boundary ──
        try:
            call(service)
        except ServiceIdentityRefused:
            pass
        except NotImplementedError:
            _fail(name, "not implemented — an operation on a declared interface must answer or "
                        "refuse, never be absent")
        else:
            _fail(name, "accepted a SERVICE identity. Every operation takes the initiator and "
                        "refuses a service, because a read attributed to a service records "
                        "provenance no person can be asked about")

        # ── every operation returns the shared result type ──
        out = call(person)
        if not isinstance(out, MeshResult):
            _fail(name, f"returned {type(out).__name__}, not MeshResult. A bare list cannot say "
                        f"whether the substrate answered, which is the defect the type ends")

        # ── a mode, where emitted, is one the interface DECLARED ──
        if out.mode is not None and out.mode not in declared_modes:
            _fail(name, f"emitted mode {out.mode!r}, which this interface does not declare "
                        f"({list(declared_modes)}). A mode a consumer cannot anticipate is a "
                        f"mode nobody can match")


# ── the write-half offline arm, ruled 2026-09-27 ────────────────────────────────────────────


def check_writer_offline(
    impl: Any,
    *,
    operations: Sequence[tuple[str, Callable[[Initiator], MeshWriteResult]]],
) -> None:
    """Properties every writer Protocol shares, provable with no substrate. ALWAYS RUN THIS.

    The write-side sibling of :func:`check_offline`, and it draws the boundary WIDER on purpose —
    ruling item 4, 2026-09-27: a write admits a person OR a delegate, refusing only a bare
    service. `check_offline` on the read side never had to draw this line because reads keep the
    narrower `require_person` gate; a writer that reused `check_offline` here would refuse a
    delegate the write boundary was ruled to admit, and this suite would then fail every
    conforming writer rather than a defective one.

    ``operations`` is a list of ``(name, call)`` pairs, the implementer's own — only they know the
    keyword arguments their write operations need.
    """
    if not operations:
        _fail("check_writer_offline", "no operations supplied — a conformance run over zero "
                                       "operations is a green that proves nothing")

    person = Initiator(subject="conformance-person", kind="person")
    service = Initiator(subject="conformance-service", kind="service")
    delegate = Initiator(subject="conformance-delegate", kind="delegate", on_behalf_of="conformance-person")

    # THE FIXTURE MUST DISCRIMINATE, three ways: a suite that cannot tell the three kinds apart
    # cannot tell an admission from a refusal either.
    assert_fixture_discriminates("initiator kinds (person/service)", person, service,
                                  describe=lambda i: i.kind)
    assert_fixture_discriminates("initiator kinds (delegate/service)", delegate, service,
                                  describe=lambda i: i.kind)

    for name, call in operations:
        # ── a bare service is refused; a person AND a delegate are admitted ──
        try:
            call(service)
        except ServiceIdentityRefused:
            pass
        except DelegateIdentityRefused:
            _fail(name, "refused a SERVICE identity by raising DelegateIdentityRefused — that "
                        "exception names 'a delegate reached a person-only operation', which is "
                        "not what happened here. A write boundary refuses a service with "
                        "ServiceIdentityRefused, the same exception the read side raises for the "
                        "same identity")
        except NotImplementedError:
            _fail(name, "not implemented — a write operation on a declared interface must apply "
                        "or refuse, never be absent")
        else:
            _fail(name, "accepted a SERVICE identity. A write attributed to a service records a "
                        "state change no person can be asked about — refuse it the same way the "
                        "read boundary refuses one, only for a stronger reason")

        try:
            delegate_out = call(delegate)
        except (ServiceIdentityRefused, DelegateIdentityRefused):
            _fail(name, "refused a DELEGATE identity carrying on_behalf_of. Ruling item 4, "
                        "2026-09-27: the write boundary is require_person_or_delegate, not "
                        "require_person — a delegate acting on its own entitlements is exactly "
                        "who this boundary exists to admit")
        else:
            if not isinstance(delegate_out, MeshWriteResult):
                _fail(name, f"returned {type(delegate_out).__name__} for a delegate initiator, "
                            f"not MeshWriteResult")

        # ── every operation returns the shared write-result type for an admitted identity ──
        out = call(person)
        if not isinstance(out, MeshWriteResult):
            _fail(name, f"returned {type(out).__name__}, not MeshWriteResult. A bare bool or "
                        f"None cannot say WHETHER a write landed and WITH WHAT, which is the "
                        f"defect this type exists to end on the write side")


# ── the live arm ─────────────────────────────────────────────────────────────────────────


def check_live(
    impl: Any,
    *,
    operation: str,
    call_reachable_empty: Callable[[], MeshResult],
    call_unreachable: Callable[[], MeshResult],
    read_provenance: Optional[Callable[[], Sequence[str]]] = None,
) -> None:
    """Properties that need a real substrate.

    ``call_reachable_empty`` must hit a substrate that IS reachable and holds nothing;
    ``call_unreachable`` must hit one that cannot be reached. The two must not be the same
    fixture wearing two names — that is checked, not assumed.
    """
    empty = call_reachable_empty()
    unreachable = call_unreachable()

    # THE ARM ALL THREE PACKETS TURN ON. A conformance run that only ever feeds an empty store
    # passes an implementation that swallows every error.
    assert_fixture_discriminates(
        f"{operation} empties", empty, unreachable, describe=lambda r: r.outcome
    )

    if empty.outcome != "empty":
        _fail(operation, f"a reachable substrate holding nothing produced {empty.outcome!r}. "
                         f"Asked-and-nothing-matched is a real answer and must say so")
    if unreachable.outcome not in ("failed", "unreachable"):
        _fail(operation, f"an unreachable substrate produced {unreachable.outcome!r} — a "
                         f"failure reported as a success is the confident-zero defect")
    if not (unreachable.detail or "").strip():
        _fail(operation, "a failure carried no detail — 'something went wrong' is how these "
                         "stayed invisible")

    # ── every read records what was read ──
    if read_provenance is None:
        _fail(operation, "no provenance reader supplied — 'every read records what it read' is "
                         "the property that CANNOT be checked offline, so a live arm that skips "
                         "it has checked the half that was already provable")
    recorded = read_provenance()
    if not recorded:
        _fail(operation, "recorded no provenance for a completed read. The abstraction records "
                         "it, not the engine remembering to — an implementation that leaves it "
                         "to the caller has moved the property back to where it was lost")


def check_embedding_contract(
    *,
    operation: str,
    declared_model: str,
    expected_dimension: int,
    read_stored_dimension: Callable[[], Optional[int]],
    declared_version: str = "",
    read_marker: Callable[[], Optional[dict]] = lambda: None,
    read_oldest_object_unix_ms: Callable[[], Optional[int]] = lambda: None,
    report_gap: Optional[Callable[[str], None]] = None,
) -> None:
    """The embedding contract, AT OPEN, in three states — and the third is the one that bites.

    Ruled 2026-09-14: the writer records the embedding model as collection metadata, and this is
    asserted **at open** rather than per query. Open is the one moment both sides pass through —
    a per-query check costs a round trip on every search and **still leaves the first WRITE
    unguarded**, and a write with the wrong model is as much the failure as a read.

        matching      open
        mismatching   refuse, naming BOTH
        absent        open, and REPORT THE GAP ONCE

    **ABSENT MUST NOT BE SILENTLY TREATED AS MATCHING.** Readers land before writers, so metadata
    is missing for a while; swallowing that is the vacuous self-comparison this property was
    rewritten to avoid, arriving dressed as tolerance. A suite that exercises only the matching
    case cannot tell the assertion from its absence.

    The DIMENSION check stays as the today-check and its limit is part of the contract: it
    catches a model swap only when the dimensions differ, and vectors under two models at one
    dimension are not numerically compatible.
    """
    if not (declared_model or "").strip():
        _fail(operation, "declared no embedding model — the value is the only handle the "
                         "writer-side check will have, so an unnamed model cannot be upgraded")

    stored = read_stored_dimension()
    if stored is None:
        _fail(operation, "could not read the stored vector dimension. That is not 'the collection "
                         "is empty' — it is the one check available today failing to run, and a "
                         "skipped check reads exactly like a passed one")
    if stored != expected_dimension:
        _fail(operation, f"stored vectors are {stored}-dimensional and this implementation embeds "
                         f"at {expected_dimension}. Searching would compare vectors from two "
                         f"different models against one index")

    try:
        marker = read_collection_marker(read_marker())
    except CorruptCollectionMarker as exc:
        _fail(operation, str(exc))

    if marker is None:
        if report_gap is None:
            _fail(operation, f"no {MESH_COLLECTION_META} marker and no gap reporter was supplied. "
                             f"ABSENT IS NOT MATCHING — an implementation that opens silently "
                             f"here has restored the self-comparison this arm exists to prevent")
        report_gap(f"{operation}: no {MESH_COLLECTION_META} marker, so "
                   f"{declared_model!r}@{declared_version!r} could not be verified. Opened "
                   f"anyway; the writer records this in the act that creates the collection.")
        return

    if marker_predates_collection(marker, read_oldest_object_unix_ms()):
        # STALE READS AS ABSENT, NOT AS A MISMATCH. A marker left behind by a recreated
        # collection describes vectors that no longer exist; refusing on it would take a healthy
        # collection down, and trusting it is the confident-stale reading the field exists to
        # prevent. An UNDATABLE (empty) collection lands here too.
        if report_gap is None:
            _fail(operation, f"the {MESH_COLLECTION_META} marker predates the collection it "
                             f"describes (or the collection is empty and cannot be dated) and no "
                             f"gap reporter was supplied")
        report_gap(f"{operation}: the {MESH_COLLECTION_META} marker predates its collection, or "
                   f"the collection is empty and cannot be dated. Treated as ABSENT — a marker "
                   f"that outlived what it described is not evidence about what is there now.")
        return

    if marker.model != declared_model:
        _fail(operation, f"the collection was written with {marker.model!r} and this "
                         f"implementation embeds with {declared_model!r}. Refusing at OPEN, "
                         f"before a vector is read or written")

    # VERSION IS COMPARED ONLY WHEN BOTH SIDES CARRY ONE. Absent is a STATE, not a value: a
    # missing version that compared equal to another missing version would report agreement on a
    # field where neither side ever knew anything — a green for the wrong reason, on one of the
    # two fields this marker exists to compare.
    if marker.version is not None and declared_version:
        if marker.version != declared_version:
            _fail(operation, f"the collection was written with version {marker.version!r} and "
                             f"this implementation embeds with {declared_version!r}")
    elif report_gap is not None:
        report_gap(f"{operation}: the model version is UNVERIFIED — "
                   f"marker={marker.version!r}, implementation={declared_version or None!r}. "
                   f"Absent is not agreement.")

    # THE OBSERVED LENGTH IS THE INDEPENDENT WITNESS. Comparing the marker against the
    # implementation's own constant would let a constant-stamping writer and a constant-trusting
    # reader agree while both disagree with the vectors on disk.
    observed = read_stored_dimension()
    if marker.dimension != observed:
        _fail(operation, f"the marker records {marker.dimension}-dimensional vectors and the "
                         f"stored vectors are {observed}-dimensional. The marker describes what "
                         f"the writer believed, not what is there")
    if observed != expected_dimension:
        _fail(operation, f"stored vectors are {observed}-dimensional and this implementation "
                         f"embeds at {expected_dimension}")


def check_writer_marker(**kw) -> None:
    """A WRITER is admitted only if what it records is readable by the contract's own reader.

    The property kept unchanged across two carrier changes, because it is what made each of them
    safe and it is carrier-independent: ONE implementation of the write, and an admission check
    over its output. Neither side writes a parser, so neither side can drift.
    """
    written = collection_marker(**kw)
    try:
        back = read_collection_marker(written)
    except CorruptCollectionMarker as exc:
        _fail("writer marker", f"wrote something its own reader rejects: {exc}")
    if back is None:
        _fail("writer marker", "wrote no readable marker")
    for field, expected in kw.items():
        if getattr(back, field) != expected:
            _fail("writer marker", f"round trip lost {field}: wrote {expected!r}, read "
                                   f"{getattr(back, field)!r}")


# ── the ontology arm ─────────────────────────────────────────────────────────────────────

_LANG_SUFFIX = re.compile(r'"@[A-Za-z]+(?:-[A-Za-z0-9]+)*\Z')


def _untyped_form(term: str) -> str:
    """The same lexical form with its datatype or language tag removed."""
    if "^^" in term:
        return term[: term.index("^^")]
    return _LANG_SUFFIX.sub('"', term)


def check_ontology_contract(
    impl: Any,
    *,
    call_ask_present: Callable[[], MeshResult],
    call_ask_absent: Callable[[], MeshResult],
    call_construct: Callable[[], MeshResult],
    typed_terms: Sequence[str],
) -> None:
    """The ``MeshOntology`` contract: absence is an ANSWER, and a typed read keeps its types.

    The three ``call_*`` are zero-argument and already bound to a PERSON initiator by the
    caller. ``typed_terms`` are the exact substrings the implementation's serializer emits for
    typed terms in the fixture subject (``'"42"^^xsd:integer'``, ``'"hello"@en'``).

    Two properties, each the reverse of a defect that shipped. ``ask`` on an IRI that does not
    exist is ``empty`` — asked, and it is not there — and never ``failed``/``unreachable`` (a
    check that cannot say no) nor ``answered`` (a check that cannot say no, the other way).
    ``construct`` returns Turtle with TERM TYPES intact, because the SELECT executor drops them.
    """
    op_ask, op_construct = "ontology.ask", "ontology.construct"

    if not typed_terms:
        _fail(op_construct, "no typed terms supplied — a suite over nothing passes everything, "
                            "and a construct that strips every type would pass it")

    # THE FIXTURE MUST DISCRIMINATE: a term with no datatype and no language tag is
    # indistinguishable from its stripped form, so it cannot tell typed from stripped.
    for term in typed_terms:
        if "^^" not in term and not _LANG_SUFFIX.search(term):
            _fail(op_construct, f"fixture does not discriminate: {term!r} carries no datatype "
                                f"and no language tag, so a construct that dropped term types "
                                f"would still emit it. Supply typed terms such as "
                                f"'\"42\"^^xsd:integer' or '\"hello\"@en'")
        assert_fixture_discriminates(
            f"{op_construct} typed term {term!r} vs untyped", term, _untyped_form(term),
            describe=lambda t: t,
        )

    present = call_ask_present()
    try:
        absent = call_ask_absent()
    except Exception as exc:  # noqa: BLE001 - ANY raise on an absent IRI is the defect
        _fail(op_ask, f"ask() raised {type(exc).__name__} on an ABSENT iri: {exc}. That is 'could "
                      f"not ask' read from a legitimate absence: ask() must not raise or fail on "
                      f"an IRI that does not exist, it answers empty")

    assert_fixture_discriminates(
        "ontology.ask present vs absent", present, absent, describe=lambda r: r.outcome
    )

    if absent.outcome in ("failed", "unreachable"):
        _fail(op_ask, f"an ABSENT iri produced {absent.outcome!r}. That is 'could not ask' read "
                      f"from a legitimate absence: ask() must not raise or fail on an IRI that "
                      f"does not exist, because empty means asked-and-it-is-not-there and "
                      f"collapsing the two is how a guard came to be a check that could not fail")
    if absent.outcome != "empty":
        _fail(op_ask, f"an ABSENT iri produced {absent.outcome!r} — an IRI that does not exist "
                      f"reported as existing. The existence check cannot say no")
    if present.outcome != "answered":
        _fail(op_ask, f"a PRESENT iri produced {present.outcome!r}, not 'answered'. This is the "
                      f"positive control: an ask() that is always empty passes the absent arm "
                      f"trivially")

    built = call_construct()
    if built.outcome != "answered":
        _fail(op_construct, f"a PRESENT subject produced {built.outcome!r}, not 'answered' — "
                            f"nothing to compare term types against, and a typed read that "
                            f"returns nothing is not a typed read")
    for row in built.rows:
        if not isinstance(row, str):
            _fail(op_construct, f"a row is {type(row).__name__}, not str. construct() returns "
                                f"Turtle TEXT; rows of another shape are the SELECT executor's "
                                f"bindings, which is where term types are dropped")
    turtle = "\n".join(built.rows)
    if not turtle.strip():
        _fail(op_construct, "answered with rows that are all blank — no Turtle was returned")
    for term in typed_terms:
        if term not in turtle:
            _fail(op_construct, f"the Turtle does not contain {term!r}. Term types were DROPPED "
                                f"(a typed literal came back untyped or the term is missing): "
                                f"types intact is the point of CONSTRUCT over SELECT")


# ── the ontology WRITER arm, ruled 2026-09-27 ───────────────────────────────────────────────


def check_ontology_writer_contract(
    *,
    call_upsert: Callable[[], MeshWriteResult],
    call_ask_within_graph: Callable[[], MeshResult],
    call_ask_default_graph: Callable[[], MeshResult],
) -> None:
    """The ``MeshOntologyWriter`` contract: a write claiming to be GRAPH-scoped must be PROVEN
    scoped, not merely asserted — the same "verify the mutation applied" discipline as
    :func:`check_writer_marker`, aimed at the defect this Protocol exists to end.

    ``call_upsert`` performs one upsert into a known graph for a known ``iri``, already bound by
    the caller. ``call_ask_within_graph`` and ``call_ask_default_graph`` are both zero-argument
    :class:`iagent_mesh.interfaces.MeshOntology` ``ask()`` calls for that SAME ``iri`` — one
    scoped to the graph just written, one scoped to Jena's default graph (``graph=None``) — bound
    to a PERSON initiator by the caller, run AFTER the upsert.

    A writer that inserted unscoped (the exact doc-tools defect this Protocol exists to close)
    would make both calls agree: the IRI is answerable both inside its graph and in the default
    graph, because it is really only ever in the one place Jena treats as "no graph at all". This
    arm fails on that agreement, not merely on the upsert's own reported outcome — a writer could
    report ``written`` while having inserted in the wrong place, and the point of this arm is that
    that lie does not survive being asked.
    """
    op = "ontology.upsert"

    written = call_upsert()
    if not written.applied:
        _fail(op, f"the upsert itself did not apply: outcome={written.outcome!r} "
                  f"detail={written.detail!r} — nothing to verify scoping against")

    within = call_ask_within_graph()
    default = call_ask_default_graph()

    # THE FIXTURE MUST DISCRIMINATE: if a write into the default graph would make both asks
    # answer identically regardless of scoping, this arm cannot tell a scoped writer from an
    # unscoped one — which is precisely the doc-tools defect this Protocol exists to catch.
    assert_fixture_discriminates(
        f"{op} scoped vs default-graph ask", within, default, describe=lambda r: r.outcome
    )

    if within.outcome != "answered":
        _fail(op, f"asking for the written iri WITHIN the graph it was upserted into produced "
                  f"{within.outcome!r}, not 'answered'. The write claimed to land in that graph "
                  f"and a scoped read cannot find it there")
    if default.outcome != "empty":
        _fail(op, f"asking for the written iri in Jena's DEFAULT graph produced "
                  f"{default.outcome!r}, not 'empty'. A write that answers from the default graph "
                  f"landed unscoped — this is the exact doc-tools defect (three of four "
                  f"SPARQL-emitting plugins inserting into the default graph, invisible to the "
                  f"mesh resolver) that GRAPH-wrapping every write exists to make impossible")


# ── the graph-writer arm, ruled 2026-09-28 overnight ────────────────────────────────────────


def check_graph_writer_contract(
    *,
    call_write_edge: Callable[[], MeshWriteResult],
    call_read_written_edge: Callable[[], MeshResult],
    call_read_unwritten_edge: Callable[[], MeshResult],
    call_write_edge_same_verb_different_key: Callable[[], MeshWriteResult],
    call_read_edge_after_both_keys: Callable[[], MeshResult],
    call_delete_edge_by_identity: Callable[[], MeshWriteResult],
    call_read_edge_after_delete: Callable[[], MeshResult],
) -> None:
    """The ``MeshGraphWriter`` contract: an edge reported as written must be PROVEN reachable by
    a read, not merely trusted from the write's own outcome — the same "verify the mutation
    applied" discipline as :func:`check_ontology_writer_contract`.

    ``call_write_edge`` writes one edge for a ``(subject, verb)`` pair the caller has already
    bound. ``call_read_written_edge`` is a :class:`iagent_mesh.interfaces.MeshGraph` ``edge()``
    call for that SAME pair, run AFTER the write, bound to a PERSON initiator by the caller.
    ``call_read_unwritten_edge`` is an ``edge()`` call for a DIFFERENT ``(subject, verb)`` pair the
    caller never wrote — the fixture's negative case. ``MeshGraph.edge`` has no scope parameter to
    exploit the way ``MeshOntology.ask(graph=...)`` does, so the discriminating pair here is
    written-vs-never-written rather than within-graph-vs-default-graph; the property proven is
    narrower (the write actually took effect, full stop) rather than the ontology arm's stronger
    scoping claim.

    ── THE KEY ARM, RULED 2026-09-29 ON THE WORKER'S OWN PACKET BACK ───────────────────────────
    ``write_edge`` now takes an :class:`iagent_mesh.interfaces.EdgeIdentity` — subject, verb,
    object, and a caller-supplied ``key`` — as identity separate from payload. The property this
    arm proves: **the same triple, written twice under two different keys, is two edges, not one
    write overwriting the other.** ``call_write_edge_same_verb_different_key`` writes the SAME
    ``(subject, verb, object)`` as ``call_write_edge`` above, with only ``key`` changed.
    ``call_read_edge_after_both_keys`` is an ``edge()`` call for that ``(subject, verb)`` pair, run
    AFTER both writes, whose ``.rows`` a conforming store answers with length 2 — a writer that
    lets the second key's write collapse onto the first would answer with length 1, indistinguish-
    able from having never accepted the key as part of identity at all.

    ── THE DELETE ARM, RULED 2026-09-29 ON THE WORKER'S OWN PACKET BACK, BUILT OVERNIGHT ───────
    Disclosed as missing when the key arm above shipped: ``delete_edges`` had no dedicated
    "verify the mutation applied" arm of its own, only the generic identity/return-type checks in
    ``check_writer_offline``. This closes that gap, and reuses the two-key state the arm above
    already built rather than standing up a third independent write: ``call_delete_edge_by_identity``
    deletes using an :class:`iagent_mesh.interfaces.EdgeIdentityFilter` scoped to the FIRST key
    only (the one ``call_write_edge`` used) — never the second. ``call_read_edge_after_delete`` is
    an ``edge()`` call for that same ``(subject, verb)`` pair, run AFTER the delete.

    A conforming store answers that read with exactly ONE row — the second key's edge, untouched.
    Two readings of a wrong count are named separately because they are different defects, not one:
    **zero rows** means the delete over-matched and removed the second key's edge too — the
    writer and the cleanup have stopped agreeing on identity, the exact failure item 2 of the
    ruling exists to prevent. **two rows** means the delete reported ``written`` but nothing was
    actually removed — the same write-side lie this whole file refuses to trust from a reported
    outcome alone, now caught on the delete path instead of the write path.
    """
    op = "graph.write_edge"

    written = call_write_edge()
    if not written.applied:
        _fail(op, f"the write itself did not apply: outcome={written.outcome!r} "
                  f"detail={written.detail!r} — nothing to verify against a read")

    found = call_read_written_edge()
    absent = call_read_unwritten_edge()

    # THE FIXTURE MUST DISCRIMINATE: a read that answers regardless of what was actually written
    # cannot tell a real write from a writer that only ever reports success.
    assert_fixture_discriminates(
        f"{op} written vs never-written edge", found, absent, describe=lambda r: r.outcome
    )

    if found.outcome != "answered":
        _fail(op, f"asking for the edge just written produced {found.outcome!r}, not 'answered'. "
                  f"The write reported success and a read cannot find what it claims to have "
                  f"landed")
    if absent.outcome != "empty":
        _fail(op, f"asking for a DIFFERENT edge that was never written produced "
                  f"{absent.outcome!r}, not 'empty'. A read that answers regardless of what was "
                  f"actually written cannot prove the write above took effect at all")

    second = call_write_edge_same_verb_different_key()
    if not second.applied:
        _fail(op, f"the second write (same subject/verb/object, a different key) did not apply: "
                  f"outcome={second.outcome!r} detail={second.detail!r} — nothing to verify the "
                  f"key arm against")

    both = call_read_edge_after_both_keys()
    if len(both.rows) != 2:
        _fail(op, f"one verb, two keys must yield two edges; a read after both writes returned "
                  f"{len(both.rows)} row(s), not 2. A writer that lets the second key's write "
                  f"overwrite the first has collapsed the key out of identity — exactly the "
                  f"defect this arm exists to catch")

    delete_op = "graph.delete_edges"

    deleted = call_delete_edge_by_identity()
    if not deleted.applied:
        _fail(delete_op, f"the delete itself did not apply: outcome={deleted.outcome!r} "
                          f"detail={deleted.detail!r} — nothing to verify against a read")

    after_delete = call_read_edge_after_delete()
    remaining = len(after_delete.rows)
    if remaining != 1:
        if remaining == 0:
            _fail(delete_op, "deleting by identity scoped to the FIRST key only removed BOTH "
                              "edges, not just the one it named. The delete's identity_filter "
                              "over-matched — the writer and the cleanup have stopped agreeing "
                              "on identity")
        elif remaining == 2:
            _fail(delete_op, "deleting by identity scoped to the FIRST key reported 'written' but "
                              "a read after the delete still finds both edges — nothing was "
                              "actually removed. The same write-side lie this suite refuses to "
                              "trust from a reported outcome alone, now on the delete path")
        else:
            _fail(delete_op, f"deleting by identity scoped to the FIRST key must leave exactly "
                              f"one edge (the second key's); a read after the delete returned "
                              f"{remaining} row(s)")


# ── the vectors-writer arm, ruled 2026-09-28 overnight ──────────────────────────────────────


def check_vectors_writer_contract(
    *,
    call_write_with_failing_embedder: Callable[[], MeshWriteResult],
    call_write_with_failing_embedder_opted_out: Callable[[], MeshWriteResult],
    call_relocate_matching_dimension: Callable[[], MeshWriteResult],
    call_relocate_wrong_dimension: Callable[[], MeshWriteResult],
    embed_call_count: Callable[[], int],
) -> None:
    """The ``MeshVectorsWriter`` contract: ``vector_required`` defaults ``True`` and a failed
    embed must actually be REFUSED, not silently completed without a vector — the sixty-seven-day
    silent-BM25 defect (``write_results.py``), replayed at write time. ``written_without_vector``
    must be reachable ONLY through the caller's own ``vector_required=False`` opt-out, never a
    writer's own fallback. ``relocate`` must refuse a dimension mismatch, and must NEVER call the
    Embedder — it takes a precomputed vector, and a relocate that quietly re-embeds has turned a
    move into an unannounced write.

    ``MeshVectors.nominate`` (semantic search) is fuzzy and ranked, not a deterministic oracle for
    "did this exact write land" — so unlike the ontology and graph arms above, this one proves
    STRUCTURAL properties the implementer's own fixture exposes directly, rather than a read-side
    round trip: two ``write`` calls against a deliberately-failing ``Embedder`` fixture (default
    vs. opted-out), a ``relocate`` pair (matching vs. mismatched dimension), and
    ``embed_call_count`` — the caller's own counter on their injected Embedder — to prove
    ``relocate`` never embeds, by measuring an effect rather than trusting a report.
    """
    op_write = "vectors.write"
    op_relocate = "vectors.relocate"

    # ── vector_required defaults True: a failing embed with no opt-out must REFUSE ──
    default_result = call_write_with_failing_embedder()
    opted_out_result = call_write_with_failing_embedder_opted_out()

    assert_fixture_discriminates(
        f"{op_write} default vs opted-out vector_required, both against a failing embedder",
        default_result, opted_out_result, describe=lambda r: r.outcome,
    )

    if default_result.applied:
        _fail(op_write, f"a failing embedder with vector_required at its DEFAULT (True) produced "
                        f"outcome={default_result.outcome!r}, which reports the write applied. "
                        f"The default must REFUSE when no vector could be produced, never complete "
                        f"one silently without it")
    if default_result.outcome != "refused":
        _fail(op_write, f"a failing embedder with vector_required at its default produced "
                        f"outcome={default_result.outcome!r}, not 'refused'. This is a caller-input "
                        f"decision the writer made on its own — the exact defect "
                        f"'written_without_vector' exists to require an explicit opt-out for")

    if opted_out_result.outcome != "written_without_vector":
        _fail(op_write, f"a failing embedder with vector_required=False produced "
                        f"outcome={opted_out_result.outcome!r}, not 'written_without_vector'. The "
                        f"caller explicitly opted into a vectorless write and the writer must name "
                        f"that state, not silently report a clean 'written' or refuse a write the "
                        f"caller asked to allow")

    # ── relocate: dimension mismatch is refused, and never touches the Embedder ──
    before = embed_call_count()

    matching = call_relocate_matching_dimension()
    wrong = call_relocate_wrong_dimension()

    assert_fixture_discriminates(
        f"{op_relocate} matching vs mismatched dimension", matching, wrong,
        describe=lambda r: r.outcome,
    )

    if not matching.applied:
        _fail(op_relocate, f"a precomputed vector at the writer's own declared dimension produced "
                           f"outcome={matching.outcome!r} detail={matching.detail!r} — relocate "
                           f"must accept a vector that actually matches")
    if wrong.applied:
        _fail(op_relocate, f"a precomputed vector at the WRONG dimension produced "
                           f"outcome={wrong.outcome!r}, which reports it applied. A vector at the "
                           f"wrong dimension is not retrievable by any query at the writer's "
                           f"declared dimension and must be refused, not stored")

    after = embed_call_count()
    if after != before:
        _fail(op_relocate, f"the Embedder was called {after - before} time(s) during relocate. "
                           f"relocate takes a PRECOMPUTED vector and must never embed — a relocate "
                           f"that embeds has silently turned a move into a write the caller never "
                           f"asked for")


# ── the three arms added 2026-09-30, on the promotion adapter's rejection packet back ───────
#
# `MeshGraphWriter` gained `has_edges`; `MeshVectorsWriter` gained `delete`; and the convention
# that lets `delete_edges` serve as "delete everything carrying this ingest_id" — a key-only
# filter spanning edges that differ in subject, verb AND object — had never been proven. All
# three close an item from `ia-74/lane/74`'s packet naming what its promotion adapter lacked.


def check_graph_writer_has_edges_contract(
    *,
    call_write_edge: Callable[[], MeshWriteResult],
    call_has_edges_matching: Callable[[], MeshResult],
    call_has_edges_not_matching: Callable[[], MeshResult],
) -> None:
    """The `has_edges` contract: an existence check must be PROVEN to discriminate written from
    unwritten, not merely echo the write's own reported outcome — the same "verify the mutation
    applied" discipline as every other arm in this module.

    `call_write_edge` writes one edge the caller has already bound. `call_has_edges_matching` is a
    `has_edges` call whose `identity_filter` matches that edge, run AFTER the write.
    `call_has_edges_not_matching` is a `has_edges` call for a filter that matches nothing the
    fixture ever wrote — the negative case.
    """
    op = "graph.has_edges"

    written = call_write_edge()
    if not written.applied:
        _fail(op, f"the write itself did not apply: outcome={written.outcome!r} "
                  f"detail={written.detail!r} — nothing to verify has_edges against")

    present = call_has_edges_matching()
    absent = call_has_edges_not_matching()

    assert_fixture_discriminates(
        f"{op} matching vs non-matching filter", present, absent, describe=lambda r: r.outcome
    )

    if present.outcome != "answered":
        _fail(op, f"a filter matching the edge just written produced {present.outcome!r}, not "
                  f"'answered'. The write reported success and has_edges disagrees")
    if absent.outcome != "empty":
        _fail(op, f"a filter matching nothing the fixture ever wrote produced "
                  f"{absent.outcome!r}, not 'empty'. A check that answers regardless of what "
                  f"was actually written cannot prove presence OR absence")


def check_graph_writer_key_only_delete_contract(
    *,
    call_write_edge_a: Callable[[], MeshWriteResult],
    call_write_edge_b_same_key_different_triple: Callable[[], MeshWriteResult],
    call_delete_by_key_only: Callable[[], MeshWriteResult],
    call_read_edge_a_after_delete: Callable[[], MeshResult],
    call_read_edge_b_after_delete: Callable[[], MeshResult],
) -> None:
    """THE PROPERTY THE `ingest_id` CLEANUP CONVENTION DEPENDS ON, PROVEN HERE FOR THE FIRST TIME.
    `iagent_mesh.provenance.ProvenanceBlock.ingest_id` exists so a caller can scope
    `delete_edges(identity_filter=EdgeIdentityFilter(key=ingest_id))` to "everything whose block
    carries this id" — which only works if a filter bound on `key` ALONE (subject, verb and object
    all left as wildcards) reaches every edge sharing that key, even edges that differ from each
    other in subject, verb AND object. The 2026-09-29 key arm (`check_graph_writer_contract`) never
    exercised this: its delete filter was always bound to subject AND verb too, scoped to one
    (subject, verb) pair throughout. A store that happens to index deletes by (subject, verb) and
    treats `key` as a secondary filter WITHIN that pair would pass that arm and still fail this
    one — exactly the gap a promotion/rejection cleanup would hit silently in production.

    `call_write_edge_a` and `call_write_edge_b_same_key_different_triple` write two edges sharing
    one `key` but differing in subject, verb and object. `call_delete_by_key_only` deletes using an
    `EdgeIdentityFilter` with ONLY `key` bound. `call_read_edge_a_after_delete` and
    `call_read_edge_b_after_delete` each read back one of the two written triples, run AFTER the
    delete.
    """
    op = "graph.delete_edges (key-only)"

    a = call_write_edge_a()
    if not a.applied:
        _fail(op, f"writing edge A did not apply: outcome={a.outcome!r} detail={a.detail!r} — "
                  f"nothing to verify the key-only delete against")

    b = call_write_edge_b_same_key_different_triple()
    if not b.applied:
        _fail(op, f"writing edge B (same key, a DIFFERENT subject/verb/object) did not apply: "
                  f"outcome={b.outcome!r} detail={b.detail!r} — nothing to verify the key-only "
                  f"delete against")

    deleted = call_delete_by_key_only()
    if not deleted.applied:
        _fail(op, f"the key-only delete itself did not apply: outcome={deleted.outcome!r} "
                  f"detail={deleted.detail!r} — nothing to verify against a read")

    after_a = call_read_edge_a_after_delete()
    after_b = call_read_edge_b_after_delete()

    if after_a.outcome != "empty":
        _fail(op, f"edge A still reads back {after_a.outcome!r} after a delete scoped to its own "
                  f"key, not 'empty'")
    if after_b.outcome != "empty":
        _fail(op, f"edge B — a DIFFERENT subject/verb/object sharing the SAME key as edge A — "
                  f"still reads back {after_b.outcome!r} after the key-only delete, not 'empty'. "
                  f"The delete reached edge A but not edge B: this store scopes a key-only filter "
                  f"to one triple rather than to every edge sharing the key, which is exactly the "
                  f"property an ingest_id-scoped cleanup depends on and would silently leave "
                  f"orphaned edges behind on a real promotion/rejection")


def check_vectors_writer_delete_contract(
    *,
    call_write: Callable[[], MeshWriteResult],
    call_delete_written: Callable[[], MeshWriteResult],
    call_delete_never_written: Callable[[], MeshWriteResult],
    contains_after_delete: Callable[[], bool],
) -> None:
    """The `delete` contract. `MeshVectors.nominate` is fuzzy and ranked, not a deterministic
    oracle for presence — the same limit `check_vectors_writer_contract` names for `write`/
    `relocate` — so this arm proves a STRUCTURAL property the implementer's own fixture exposes
    directly (`contains_after_delete`, the same pattern as that arm's `embed_call_count`), rather
    than a read-side round trip through semantic search.

    `call_write` writes one object the caller has already bound. `call_delete_written` deletes
    that SAME id, run after the write. `contains_after_delete` is the fixture's own introspection
    on its backing store, called after that delete. `call_delete_never_written` deletes a
    DIFFERENT id the fixture never wrote — the idempotency case `MeshGraphWriter.delete_edges`
    already states ("a filter matching nothing still reports written").
    """
    write_op = "vectors.write"
    delete_op = "vectors.delete"

    written = call_write()
    if not written.applied:
        _fail(write_op, f"the write itself did not apply: outcome={written.outcome!r} "
                        f"detail={written.detail!r} — nothing to verify delete against")

    deleted = call_delete_written()
    if not deleted.applied:
        _fail(delete_op, f"deleting the id just written did not apply: outcome={deleted.outcome!r} "
                         f"detail={deleted.detail!r}")

    if contains_after_delete():
        _fail(delete_op, "the id written above is STILL present after delete reported applied — "
                         "the same write-side lie this suite refuses to trust from a reported "
                         "outcome alone, now on the delete path")

    idempotent = call_delete_never_written()
    if not idempotent.applied:
        _fail(delete_op, f"deleting an id that was never written produced "
                         f"outcome={idempotent.outcome!r}, not an applied state. Deletion must be "
                         f"idempotent — the store now satisfies 'this id is absent', which may "
                         f"already have been true, the same reasoning "
                         f"MeshGraphWriter.delete_edges applies to a filter matching zero edges")


# ── check_graph_writer_write_node_contract, added 2026-10-01 — opens v0.9.6 scope, for Lane 1
# moving the ingest node off Neo4jIngestGraph ───────────────────────────────────────────────


def check_graph_writer_write_node_contract(
    *,
    call_write_node: Callable[[], MeshWriteResult],
    node_payload_after_write: Callable[[], Optional[Mapping[str, str]]],
    call_write_node_again_same_id_different_payload: Callable[[], MeshWriteResult],
    node_payload_after_second_write: Callable[[], Optional[Mapping[str, str]]],
) -> None:
    """The `write_node` contract. `MeshGraphWriter` has no node-read operation of its own (reads
    here are all edge-shaped — `MeshGraph.edge`, `MeshGraphWriter.has_edges` — and there is
    deliberately no `has_node` in this amendment, see the Protocol's own 2026-10-01 note), so this
    arm proves a STRUCTURAL property the implementer's own fixture exposes directly
    (`node_payload_after_write`), the same pattern `check_vectors_writer_delete_contract` uses for
    `contains_after_delete` when no deterministic read-side oracle exists.

    THE PROPERTY THIS ARM EXISTS TO CATCH, SPECIFICALLY: `write_node` is an UPSERT, the opposite
    of `write_edge`'s key-grants-multiplicity rule. `call_write_node` and
    `call_write_node_again_same_id_different_payload` write to the SAME `(label, id)` with
    DIFFERING payloads — a conforming store's `node_payload_after_second_write` must reflect the
    SECOND write, never the first, and must not be reachable as two separate nodes. A store that
    treated `write_node` like `write_edge` — appending, or silently keeping the first write in
    place — leaves `node_payload_after_write` and `node_payload_after_second_write` reading back
    the SAME value, caught by `assert_fixture_discriminates` the same way
    `check_graph_writer_contract`'s own "stores nothing" case is: two observations that must
    differ and didn't. This is exactly the defect Lane 1's repeated per-stage writes would hit in
    production (as many phantom ingest nodes, or one frozen one, as status transitions).

    `call_write_node` writes one node the caller has already bound. `node_payload_after_write` is
    the fixture's own introspection on its backing store for that `(label, id)`, called after the
    write. `call_write_node_again_same_id_different_payload` writes the SAME `(label, id)` again
    with a payload the caller has bound to differ from the first.
    `node_payload_after_second_write` is the same introspection, called after the second write.
    """
    op = "graph.write_node"

    written = call_write_node()
    if not written.applied:
        _fail(op, f"the write itself did not apply: outcome={written.outcome!r} "
                  f"detail={written.detail!r} — nothing to verify against the store")

    first_payload = node_payload_after_write()

    second = call_write_node_again_same_id_different_payload()
    if not second.applied:
        _fail(op, f"a second write to the SAME (label, id) with a different payload did not "
                  f"apply: outcome={second.outcome!r} detail={second.detail!r} — nothing to "
                  f"verify the upsert property against")

    second_payload = node_payload_after_second_write()

    # THE FIXTURE MUST DISCRIMINATE: a store that persists nothing (both reads come back None) or
    # that silently ignores the second write (both reads come back the FIRST payload) looks
    # identical here, and both ARE the defect this arm exists to catch.
    assert_fixture_discriminates(
        f"{op} first vs second payload", first_payload, second_payload, describe=lambda p: p
    )

    if first_payload is None:
        _fail(op, "the first write reported success and the fixture's own introspection finds no "
                  "node at this (label, id) afterward — the write-side lie this suite refuses to "
                  "trust from a reported outcome alone")
    if second_payload is None:
        _fail(op, "the second write reported success and the fixture's own introspection finds "
                  "no node at this (label, id) afterward")


# ── check_graph_writer_has_node_contract / check_graph_writer_delete_node_contract, added
# 2026-10-01 — opens v0.9.7 scope, for the read and cleanup halves write_node's own docstring
# left open ───────────────────────────────────────────────────────────────────────────────────


def check_graph_writer_has_node_contract(
    *,
    call_write_node: Callable[[], MeshWriteResult],
    call_has_node_matching: Callable[[], MeshResult],
    call_has_node_not_matching: Callable[[], MeshResult],
) -> None:
    """The `has_node` contract: an existence check must be PROVEN to discriminate written from
    unwritten, not merely echo the write's own reported outcome — the same "verify the mutation
    applied" discipline `check_graph_writer_has_edges_contract` already applies to edges, adapted
    to a node's `(label, id)` key instead of an edge's `identity_filter`. `has_node` returns
    `MeshResult`, the same as `has_edges`, so the method's own return value IS the oracle here —
    no structural introspection callable is needed, unlike `check_graph_writer_write_node_contract`
    and `check_graph_writer_delete_node_contract`, which have no read-side Protocol method to call.

    `call_write_node` writes one node the caller has already bound. `call_has_node_matching` is a
    `has_node` call for that SAME `(label, id)`, run AFTER the write. `call_has_node_not_matching`
    is a `has_node` call for a `(label, id)` the fixture never wrote — the negative case.
    """
    op = "graph.has_node"

    written = call_write_node()
    if not written.applied:
        _fail(op, f"the write itself did not apply: outcome={written.outcome!r} "
                  f"detail={written.detail!r} — nothing to verify has_node against")

    present = call_has_node_matching()
    absent = call_has_node_not_matching()

    assert_fixture_discriminates(
        f"{op} matching vs non-matching (label, id)", present, absent, describe=lambda r: r.outcome
    )

    if present.outcome != "answered":
        _fail(op, f"a (label, id) matching the node just written produced {present.outcome!r}, "
                  f"not 'answered'. The write reported success and has_node disagrees")
    if absent.outcome != "empty":
        _fail(op, f"a (label, id) the fixture never wrote produced {absent.outcome!r}, not "
                  f"'empty'. A check that answers regardless of what was actually written cannot "
                  f"prove presence OR absence")


def check_graph_writer_delete_node_contract(
    *,
    call_write_node: Callable[[], MeshWriteResult],
    call_delete_node: Callable[[], MeshWriteResult],
    node_present_after_delete: Callable[[], bool],
    call_delete_node_never_written: Callable[[], MeshWriteResult],
) -> None:
    """The `delete_node` contract. `MeshGraphWriter` has no node-read Protocol method (the same
    limitation `check_graph_writer_write_node_contract` already works around for `write_node`), so
    this arm proves a STRUCTURAL property the implementer's own fixture exposes directly
    (`node_present_after_delete`), the same pattern `check_vectors_writer_delete_contract` uses for
    `contains_after_delete` when no deterministic read-side oracle exists.

    `call_write_node` writes one node the caller has already bound. `call_delete_node` deletes
    that SAME `(label, id)`, run after the write. `node_present_after_delete` is the fixture's own
    introspection on its backing store for that `(label, id)`, called after that delete.
    `call_delete_node_never_written` deletes a DIFFERENT `(label, id)` the fixture never wrote —
    the idempotency case `delete_edges`'s own docstring already states ("a filter matching nothing
    still reports written"), which `delete_node` must honour identically: "nothing to delete" is
    success, never an error.
    """
    op = "graph.delete_node"

    written = call_write_node()
    if not written.applied:
        _fail(op, f"the write itself did not apply: outcome={written.outcome!r} "
                  f"detail={written.detail!r} — nothing to verify delete_node against")

    deleted = call_delete_node()
    if not deleted.applied:
        _fail(op, f"deleting the (label, id) just written did not apply: "
                  f"outcome={deleted.outcome!r} detail={deleted.detail!r}")

    if node_present_after_delete():
        _fail(op, "the node written above is STILL present after delete_node reported applied — "
                  "the same write-side lie this suite refuses to trust from a reported outcome "
                  "alone, now on the delete path")

    idempotent = call_delete_node_never_written()
    if not idempotent.applied:
        _fail(op, f"deleting a (label, id) that was never written produced "
                  f"outcome={idempotent.outcome!r}, not an applied state. Deletion must be "
                  f"idempotent — the store now satisfies 'this node is absent', which may already "
                  f"have been true, the same reasoning delete_edges applies to a filter matching "
                  f"zero edges. Treating 'nothing to delete' as a failure is exactly the defect "
                  f"this arm exists to catch")
