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
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from .interfaces import (
    EMBEDDING_METADATA_KEY,
    Initiator,
    ServiceIdentityRefused,
    read_embedding_stamp,
)
from .results import MeshResult

__all__ = [
    "check_embedding_contract",
    "check_writer_stamp",
    "ConformanceFailure",
    "assert_fixture_discriminates",
    "check_offline",
    "check_live",
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
    read_collection_metadata: Callable[[], Optional[dict]] = lambda: None,
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

    stamp = read_embedding_stamp(read_collection_metadata())
    if stamp is None:
        # ABSENT *AND* MALFORMED LAND HERE, deliberately. A half-written stamp is no more
        # evidence of agreement than no stamp, and a reader that told them apart would be
        # tempted to treat one as a partial match.
        if report_gap is None:
            _fail(operation, "collection metadata carries no readable embedding stamp and no gap "
                             "reporter was supplied. ABSENT IS NOT MATCHING — an implementation "
                             "that opens silently here has restored the self-comparison this arm "
                             "exists to prevent")
        report_gap(
            f"{operation}: the collection carries no readable {EMBEDDING_METADATA_KEY!r} stamp, "
            f"so {declared_model!r}@{declared_version!r} could not be verified against it. "
            f"Opened anyway; the writer records this at create-or-first-write."
        )
        return

    if (stamp.model, stamp.version) != (declared_model, declared_version):
        _fail(operation, f"the collection was written with {stamp.model!r}@{stamp.version!r} and "
                         f"this implementation embeds with {declared_model!r}@{declared_version!r}. "
                         f"Refusing at OPEN, before a vector is read or written")


def check_writer_stamp(recorded: dict) -> None:
    """A WRITER is admitted only if what it records is readable under the declared key.

    The ruling's teeth: a writer recording under a key of its own choosing fails admission, and
    so does a reader looking under one. Both sides conform to the Protocol's declaration rather
    than to each other — a key two lanes agree on is an agreement enforced by remembering, which
    is the defect this stamp closes.
    """
    if EMBEDDING_METADATA_KEY not in (recorded or {}):
        _fail("writer stamp", f"recorded no {EMBEDDING_METADATA_KEY!r} entry. The key is declared "
                              f"by the contract, not chosen by the writer")
    if read_embedding_stamp(recorded) is None:
        _fail("writer stamp", f"recorded {EMBEDDING_METADATA_KEY!r} in a shape the contract's own "
                              f"reader cannot parse — a stamp only the writer understands is a "
                              f"stamp nobody can check")
