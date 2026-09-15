"""One result type for every mesh read: WHETHER it was answered, and HOW.

RATIFIED 2026-09-14, and built before any interface has a method — deliberately. Two axes were
arriving from opposite directions:

    outcome   answered | empty | failed | unreachable    WHETHER the substrate answered
    mode      hybrid | bm25 | ...                        HOW it answered, where a mode exists

Designing them separately produces a `status` field on the graph interface and a `mode` field on
the vector one, meaning the same thing in two vocabularies. It is ONE decision rather than two
converging ones only because the `mode` axis had no implementation yet to be consistent with —
so this is the cheapest it will ever be, and it is why the type exists before the Protocols do.

── THE DEFECT THIS TYPE EXISTS TO END ──────────────────────────────────────────────────────
**A failure and a legitimate empty are the same value today across THREE basis sites.** A SPARQL
error returns `[]`; a store that holds nothing returns `[]`; a store that cannot be reached
returns `[]`. Downstream they are indistinguishable, so:

  * a disposition dashboard renders a CONFIDENT ZERO built from a substrate failure;
  * a resolver fan-out reads a refusal as an abstention, which is worse than the refusal;
  * an ancestor walk that failed silently reverts classification to pre-ADR-0018 behaviour;
  * the fleet ran SIXTY-SEVEN DAYS with every vector search silently BM25-only, because a
    fallback with no marker in its return is a mode nobody can see.

Each of those is the same bug wearing a different consequence: **the return could not say what
happened, so every caller assumed the happy reading.**

── WHY `bool()` RAISES ─────────────────────────────────────────────────────────────────────
The likeliest way a consumer reinstates the defect is not malice, it is idiom:

    if not result:          # collapses empty, failed and unreachable into one branch
        return []

That single line is the entire bug class restored, and it reads as careful code. So this type
HAS NO TRUTH VALUE: ``bool(result)`` raises, naming the three states it refuses to collapse.
The precedent is ``numpy.ndarray``, which raises on ``bool()`` for exactly this reason — an
ambiguous truth value is better refused than guessed. **A type whose misuse is a one-liner must
make the one-liner fail.**

Callers that genuinely want "rows or an exception" have :meth:`MeshResult.require`; callers that
want to branch have ``result.outcome``. Neither is longer than the broken idiom.

── WHAT IS NOT PARAMETERISED ───────────────────────────────────────────────────────────────
**This type does not decide what its states MEAN.** Ruled per-site, because one rule is wrong at
two consumers: an empty result is a first-class ABSTAIN in a resolver fan-out and a DECISION
INPUT on a dashboard, and those want opposite handling. The contract's job is to make the
distinction expressible; the policy belongs to the caller.

**AND IT DOES NOT FOLLOW THAT EVERY EMPTY-RETURNING SITE MUST ADOPT IT.** The three basis sites
above are a SCOPED count, not every place a bare ``[]`` is returned — a raw scan of "except
handlers returning an empty container" is wider and includes at least one site that **degrades
OPEN on purpose**: a served-class filter whose empty means *do not filter*, where failing closed
would empty the candidate pool and take routing down globally. That one is architect-ruled to
STAY as it is. A conformance requirement phrased over the raw count would demand it change, so
the requirement is phrased over reads that go through these interfaces — deliberate degrade-open
behaviour behind a documented reason is not a defect this type is chasing.
"""

from __future__ import annotations

from typing import Generic, Literal, Optional, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

__all__ = [
    "OUTCOMES",
    "Outcome",
    "MeshResult",
    "AmbiguousResultTruth",
    "ResultNotAnswered",
]

T = TypeVar("T")

#: The four states, in the order they degrade. `answered` and `empty` are both SUCCESSES — the
#: substrate was asked and replied; they differ only in whether anything matched. `failed` and
#: `unreachable` are both FAILURES, and they are separate because they have different operator
#: remedies: a failed query is a query defect, an unreachable store is a deployment one.
OUTCOMES = ("answered", "empty", "failed", "unreachable")

Outcome = Literal["answered", "empty", "failed", "unreachable"]


class AmbiguousResultTruth(TypeError):
    """``bool(MeshResult)`` — refused, because the answer would have to collapse three states."""


class ResultNotAnswered(RuntimeError):
    """:meth:`MeshResult.require` on a result that did not answer. Carries the outcome and the
    detail, so the raise names WHICH failure rather than only that there was one."""


class MeshResult(BaseModel, Generic[T]):
    """What a mesh read returns. Every read, every interface, one type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Outcome
    rows: tuple[T, ...] = ()
    mode: Optional[str] = None
    """HOW it was answered, where a mode exists — ``hybrid``/``bm25`` for a vector search, absent
    for a read with only one way to answer. **A degraded mode must be NAMED here rather than
    served silently**: sixty-seven days of BM25-only with nothing in any result saying so is what
    this field exists to make impossible."""

    detail: Optional[str] = None
    """Why, for a failure. Required on ``failed`` and ``unreachable`` — a failure with no reason
    reaches an operator as "something went wrong" and is the reason these went unnoticed."""

    @model_validator(mode="after")
    def _states_are_coherent(self) -> "MeshResult[T]":
        if self.outcome == "answered" and not self.rows:
            raise ValueError(
                "outcome='answered' with no rows — that is `empty`. The distinction is the "
                "entire point of this type"
            )
        if self.outcome != "answered" and self.rows:
            raise ValueError(
                f"outcome={self.outcome!r} carrying {len(self.rows)} rows — a non-answered "
                f"result with data is the silent-fallback shape this type refuses"
            )
        if self.outcome in ("failed", "unreachable") and not (self.detail or "").strip():
            raise ValueError(
                f"outcome={self.outcome!r} with no detail — a failure that cannot say why is "
                f"how these stayed invisible for sixty-seven days"
            )
        return self

    # ── constructors, so the coherent cases are the short ones ───────────────────────────

    @classmethod
    def answered(cls, rows: Sequence[T], *, mode: str | None = None) -> "MeshResult[T]":
        return cls(outcome="answered", rows=tuple(rows), mode=mode)

    @classmethod
    def empty(cls, *, mode: str | None = None) -> "MeshResult[T]":
        """ASKED, AND NOTHING MATCHED. A real answer, and not the same thing as a failure."""
        return cls(outcome="empty", mode=mode)

    @classmethod
    def failed(cls, detail: str, *, mode: str | None = None) -> "MeshResult[T]":
        """Asked; the substrate refused or errored."""
        return cls(outcome="failed", detail=detail, mode=mode)

    @classmethod
    def unreachable(cls, detail: str) -> "MeshResult[T]":
        """COULD NOT ASK. Separate from ``failed`` because the remedy is a deployment one."""
        return cls(outcome="unreachable", detail=detail)

    # ── reading it ───────────────────────────────────────────────────────────────────────

    @property
    def answered_ok(self) -> bool:
        """True for BOTH successes. The substrate was asked and replied; ``rows`` may be empty.

        Named rather than given to ``bool()`` on purpose: a reader of ``if r.answered_ok`` can
        see which question is being asked, where ``if r`` cannot.
        """
        return self.outcome in ("answered", "empty")

    def require(self, what: str = "read") -> tuple[T, ...]:
        """Rows, or raise naming the outcome. The safe one-liner, so nobody writes the unsafe one.

        An ``empty`` result returns ``()`` — it answered. Only a FAILURE raises.
        """
        if not self.answered_ok:
            raise ResultNotAnswered(
                f"{what} did not answer: outcome={self.outcome!r} detail={self.detail!r}"
            )
        return self.rows

    def __bool__(self) -> bool:  # noqa: D105 — the docstring is the module's
        raise AmbiguousResultTruth(
            f"MeshResult has no truth value (outcome={self.outcome!r}). `if result:` would "
            f"collapse empty, failed and unreachable into one branch, which is the defect this "
            f"type exists to end. Use `result.outcome`, `result.answered_ok`, or "
            f"`result.require()`."
        )

    def __len__(self) -> int:
        """Row count. NOT a truth value — ``len()`` is explicit about what it counts, and a
        caller writing ``len(r) == 0`` has said "no rows" rather than "falsy"."""
        return len(self.rows)
