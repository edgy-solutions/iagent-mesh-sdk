"""The write result type's job is the read type's job, one verb later: make states that were
identical distinguishable, and refuse the idiom that would re-collapse them.

`MeshWriteResult` is a SIBLING of `MeshResult`, never an overload of it — this file exercises the
one property that split demands and `MeshResult`'s own suite does not: `written_without_vector`
must sit APART from `written` in every idiom that would otherwise fold them together, because a
degraded landing wearing a plain "it worked" is the sixty-seven-day silent-BM25 defect replayed at
write time.
"""
from __future__ import annotations

import pytest

from iagent_mesh.write_results import (
    WRITE_OUTCOMES,
    AmbiguousWriteResultTruth,
    MeshWriteResult,
    WriteNotApplied,
)


# ── the discrimination the write side adds on top of the read side's ────────────────────────

def test_written_and_written_without_vector_are_DIFFERENT_outcomes():
    """THE PROPERTY THIS TYPE EXISTS TO ADD. A clean write and a vectorless write must not
    arrive at a caller looking the same, even though both landed."""
    clean = MeshWriteResult.written()
    degraded = MeshWriteResult.written_without_vector("embed timed out, caller opted in")
    assert clean.outcome != degraded.outcome
    assert clean != degraded


def test_refused_and_failed_are_also_distinct():
    """Separate because the remedy differs: a refusal never touched the store (an identity gate,
    a caller input the writer will not act on), a failure means the store was asked and errored."""
    assert MeshWriteResult.refused("service identity").outcome != MeshWriteResult.failed("500").outcome


def test_failed_and_unreachable_are_also_distinct():
    assert MeshWriteResult.failed("syntax error").outcome != MeshWriteResult.unreachable("no route").outcome


# ── the idiom that would restore the defect, now with a fourth state to fold in ─────────────

def test_bool_RAISES_for_every_outcome():
    for r in (
        MeshWriteResult.written(),
        MeshWriteResult.written_without_vector("d"),
        MeshWriteResult.refused("d"),
        MeshWriteResult.failed("d"),
        MeshWriteResult.unreachable("d"),
    ):
        with pytest.raises(AmbiguousWriteResultTruth):
            bool(r)


def test_the_ACTUAL_broken_idiom_refuses():
    r = MeshWriteResult.written_without_vector("embed failed")
    with pytest.raises(AmbiguousWriteResultTruth):
        if r:  # noqa: SIM103 — the point is that this line cannot run
            pass


# ── coherence: the states cannot lie about themselves ────────────────────────────────────

def test_written_needs_no_detail():
    assert MeshWriteResult.written().detail is None


@pytest.mark.parametrize("bad", ["written_without_vector", "refused", "failed", "unreachable"])
def test_every_state_but_written_must_say_why(bad):
    """A degrade or a failure that cannot say why is exactly how these stay invisible — the read
    side's rule, extended to cover `written_without_vector` too, since a silent degrade is the
    specific failure this vocabulary was ruled to prevent."""
    with pytest.raises(Exception, match="detail|why"):
        MeshWriteResult(outcome=bad)


def test_a_blank_detail_is_refused_the_same_as_an_absent_one():
    with pytest.raises(Exception, match="detail=''|omit"):
        MeshWriteResult(outcome="failed", detail="   ")


def test_every_outcome_in_the_vocabulary_is_constructible():
    """POSITIVE CONTROL — a model that rejected everything would pass every raises-check above."""
    built = {
        MeshWriteResult.written().outcome,
        MeshWriteResult.written_without_vector("d").outcome,
        MeshWriteResult.refused("d").outcome,
        MeshWriteResult.failed("d").outcome,
        MeshWriteResult.unreachable("d").outcome,
    }
    assert built == set(WRITE_OUTCOMES)


# ── reading it ───────────────────────────────────────────────────────────────────────────

def test_applied_is_true_for_BOTH_landed_states():
    """`written_without_vector` landed — the record IS in the store. A caller that treats it as
    a failure has re-created the abstention-read-as-refusal defect from the read side."""
    assert MeshWriteResult.written().applied is True
    assert MeshWriteResult.written_without_vector("d").applied is True
    assert MeshWriteResult.refused("d").applied is False
    assert MeshWriteResult.failed("d").applied is False
    assert MeshWriteResult.unreachable("d").applied is False


def test_require_returns_self_for_BOTH_landed_states():
    assert MeshWriteResult.written().require().outcome == "written"
    assert MeshWriteResult.written_without_vector("d").require().outcome == "written_without_vector"


@pytest.mark.parametrize(
    "r", [MeshWriteResult.refused("no"), MeshWriteResult.failed("boom"), MeshWriteResult.unreachable("down")]
)
def test_require_raises_NAMING_the_outcome_and_the_reason(r):
    with pytest.raises(WriteNotApplied) as exc:
        r.require("vectors.write")
    msg = str(exc.value)
    assert r.outcome in msg, "the raise must say WHICH non-landing, not only that there was one"
    assert (r.detail or "") in msg
    assert "vectors.write" in msg, "and which write it was"
