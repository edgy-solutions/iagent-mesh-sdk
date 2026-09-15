"""The result type's job is to make two values that were identical distinguishable.

Across five call sites today a substrate FAILURE and a legitimate EMPTY are the same value —
`[]`. Every consequence downstream (a confident zero on a dashboard, a refusal read as an
abstention, sixty-seven days of silent BM25) is that one collapse wearing a different cost.

So the arm that matters is not "the model validates". It is: **the two empties produce different
results, and the idiom that would re-collapse them refuses.**

THE RULE THE CONFORMANCE SUITE INHERITS IS THE GENERAL ONE, NOT THIS INSTANCE. "Test both
empties" is what it looks like here. The rule is **a fixture is a legal input that happens to
make two behaviours identical** — an alphabetical order fixture cannot tell sorted from
preserved, an empty-store fixture cannot tell answered-nothing from failed-silently. So the
suite asserts its own fixtures DISCRIMINATE before using them, rather than carrying a list of
remembered instances.
"""
from __future__ import annotations

import pytest

from iagent_mesh.results import (
    OUTCOMES,
    AmbiguousResultTruth,
    MeshResult,
    ResultNotAnswered,
)


# ── the discrimination, which is the whole point ─────────────────────────────────────────

def test_the_two_empties_are_DIFFERENT_results():
    """THE PROPERTY ALL THREE PACKETS TURN ON. A store that holds nothing and a store that
    cannot be reached must not arrive at a caller as the same value."""
    asked_nothing_matched = MeshResult.empty()
    could_not_ask = MeshResult.unreachable("connection refused")

    assert asked_nothing_matched.outcome != could_not_ask.outcome
    assert asked_nothing_matched != could_not_ask
    # …and both carry no rows, which is exactly why the ROW COUNT cannot tell them apart.
    assert len(asked_nothing_matched) == len(could_not_ask) == 0


def test_a_failure_and_an_unreachable_are_also_distinct():
    """Separate because the remedy is different: a failed query is a query defect, an
    unreachable store is a deployment one. Collapsing them sends an operator to the wrong place."""
    assert MeshResult.failed("syntax error").outcome != MeshResult.unreachable("no route").outcome


# ── the idiom that would restore the defect ──────────────────────────────────────────────

def test_bool_RAISES_because_it_would_have_to_collapse_three_states():
    for r in (MeshResult.empty(), MeshResult.failed("x"), MeshResult.unreachable("y"),
              MeshResult.answered([1])):
        with pytest.raises(AmbiguousResultTruth):
            bool(r)


def test_the_ACTUAL_broken_idiom_refuses():
    """`if not result: return []` is the whole bug class in one line, and it reads as careful
    code. Asserting `bool()` raises is not the same as asserting THIS refuses — the idiom is
    what a reviewer sees."""
    r = MeshResult.failed("substrate down")
    with pytest.raises(AmbiguousResultTruth):
        if not r:  # noqa: SIM103 — the point is that this line cannot run
            pass
    with pytest.raises(AmbiguousResultTruth):
        _ = r or []


def test_len_still_works_and_says_what_it_counts():
    """`len(r) == 0` has said "no rows". `if r` would have said something vaguer and wrong."""
    assert len(MeshResult.answered([1, 2])) == 2
    assert len(MeshResult.empty()) == 0


# ── coherence: the states cannot lie about themselves ────────────────────────────────────

def test_answered_with_no_rows_is_refused():
    with pytest.raises(Exception, match="that is `empty`|empty"):
        MeshResult(outcome="answered", rows=())


@pytest.mark.parametrize("bad", ["empty", "failed", "unreachable"])
def test_a_non_answered_result_may_not_carry_rows(bad):
    """A failure carrying data is the silent-fallback shape: the caller sees rows, believes it
    was answered, and the failure is invisible."""
    kw = {"detail": "d"} if bad in ("failed", "unreachable") else {}
    with pytest.raises(Exception, match="silent-fallback|rows"):
        MeshResult(outcome=bad, rows=(1,), **kw)


@pytest.mark.parametrize("bad", ["failed", "unreachable"])
def test_a_failure_must_say_why(bad):
    """A failure that cannot say why reaches an operator as "something went wrong"."""
    with pytest.raises(Exception, match="detail|why"):
        MeshResult(outcome=bad)


def test_every_outcome_in_the_vocabulary_is_constructible():
    """POSITIVE CONTROL for the refusals above — a model that rejected everything would pass
    every `pytest.raises` in this file."""
    built = {
        MeshResult.answered([1]).outcome,
        MeshResult.empty().outcome,
        MeshResult.failed("d").outcome,
        MeshResult.unreachable("d").outcome,
    }
    assert built == set(OUTCOMES)


# ── reading it ───────────────────────────────────────────────────────────────────────────

def test_answered_ok_is_true_for_BOTH_successes():
    """`empty` is a real answer. A caller that treats it as failure re-creates the defect from
    the other direction — refusing to act on a substrate that correctly said "nothing"."""
    assert MeshResult.answered([1]).answered_ok is True
    assert MeshResult.empty().answered_ok is True
    assert MeshResult.failed("d").answered_ok is False
    assert MeshResult.unreachable("d").answered_ok is False


def test_require_returns_rows_for_a_success_and_EMPTY_IS_A_SUCCESS():
    assert MeshResult.answered([1, 2]).require() == (1, 2)
    assert MeshResult.empty().require() == ()


@pytest.mark.parametrize("r", [MeshResult.failed("boom"), MeshResult.unreachable("no route")])
def test_require_raises_NAMING_the_outcome_and_the_reason(r):
    with pytest.raises(ResultNotAnswered) as exc:
        r.require("instances_by_property")
    msg = str(exc.value)
    assert r.outcome in msg, "the raise must say WHICH failure, not only that there was one"
    assert (r.detail or "") in msg
    assert "instances_by_property" in msg, "and which read it was"


# ── the mode axis ────────────────────────────────────────────────────────────────────────

def test_mode_rides_the_same_result_rather_than_a_parallel_field():
    """One type, both axes. Two types would mean a `status` on the graph side and a `mode` on
    the vector side saying one thing in two vocabularies."""
    r = MeshResult.answered([1], mode="bm25")
    assert r.outcome == "answered" and r.mode == "bm25"


def test_a_DEGRADED_mode_is_expressible_on_a_successful_read():
    """The sixty-seven-day defect: every search silently BM25-only with nothing in any result
    saying so. A degradation must be a marked success, not an unmarked one."""
    degraded = MeshResult.answered([1], mode="bm25")
    full = MeshResult.answered([1], mode="hybrid")
    assert degraded.outcome == full.outcome, "both answered — the degradation is not a failure"
    assert degraded.mode != full.mode, "…and a caller can still tell them apart"


def test_mode_is_absent_where_there_is_no_mode():
    assert MeshResult.answered([1]).mode is None
