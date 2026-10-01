"""One result type for every mesh write: WHETHER it took effect, and WITH WHAT.

Sibling to :mod:`results`, not an extension of it. ``MeshResult`` documents itself as the type
"for every mesh READ" — a write is not a read wearing a different outcome vocabulary, and
stuffing one into the other would falsify that module's own claim the same way the earlier
``MeshOntology`` docstring falsified its own by asserting something that had stopped being true.
Same discipline, a new type: ``bool()`` raises, a failure must say why, a degrade is a NAMED state
rather than a silent one — nothing here is designed differently from ``results.py``, it is placed
differently, on purpose.

── THE VOCABULARY, RULED 2026-09-27, AND WHY IT IS FIVE STATES ─────────────────────────────
    written                   the store holds it, vector included wherever one is required
    written_without_vector    the store holds it WITHOUT a vector — reachable ONLY by opt-in
    refused                   declined before touching the store
    failed                    the store was asked and errored
    unreachable               could not be asked at all

``refused`` vs. ``failed`` carries over the read side's ``unreachable``/``failed`` split verbatim,
one level earlier: a refusal (an identity gate, or an embed that failed while ``vector_required``
was never waived) never touches the store at all, where a failure means the store was asked and
said no. Collapsing them would hide exactly which side owns the remedy — an authorization fix on
one side, a store or embedding-endpoint fix on the other.

``written_without_vector`` is not a fifth flavour of ``failed``, for the same reason ``empty`` is
not a flavour of ``failed`` on the read side. The failure mode this state exists to name: an embed
call times out, a writer "helpfully" falls back to writing the record with no vector because *at
least the record is there*, and the caller learns nothing — the sixty-seven-day silent-BM25 defect
`results.py` documents, replayed at write time instead of read time. Naming the state is what
turns that from an assumption into a call-site decision.

── `vector_required` DEFAULTS True; `written_without_vector` IS OPT-IN, NEVER A DEFAULT ────
A writer never decides on its own that a vectorless write is acceptable — the caller says so, at
the call, with ``vector_required=False``, the same way a read-side degrade-open decision is made
visible at its call site rather than living in a helper's docstring (``results.py``, "DEGRADE-OPEN
IS A DISPOSITION, NOT AN EXEMPTION"). A writer that falls back on its own initiative has performed
the defect this whole vocabulary exists to end, and reporting ``written`` when it did so is a
confident lie a caller cannot detect.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "WRITE_OUTCOMES",
    "WriteOutcome",
    "MeshWriteResult",
    "AmbiguousWriteResultTruth",
    "WriteNotApplied",
]

#: The five states. `written` and `written_without_vector` are both LANDED — the store now holds
#: the record; they differ only in whether it carries a vector. `refused`, `failed` and
#: `unreachable` are all NOT-LANDED, and are kept separate for the same reason the read side keeps
#: `failed`/`unreachable` separate: different remedies, an authorization or caller-input fix for
#: `refused`, a store-side or query fix for `failed`, a deployment fix for `unreachable`.
WRITE_OUTCOMES = ("written", "written_without_vector", "refused", "failed", "unreachable")

WriteOutcome = Literal[
    "written", "written_without_vector", "refused", "failed", "unreachable"
]


class AmbiguousWriteResultTruth(TypeError):
    """``bool(MeshWriteResult)`` — refused, because the answer would have to collapse four states
    that need different handling, and fold `written_without_vector` into the same truthy branch
    as `written` besides — which is precisely the state this vocabulary exists to keep visible."""


class WriteNotApplied(RuntimeError):
    """:meth:`MeshWriteResult.require` on a result that did not land. Carries the outcome and the
    detail, so the raise names WHICH failure rather than only that there was one."""


class MeshWriteResult(BaseModel):
    """What a mesh write returns. Every writer, every Protocol, one type — the write-side sibling
    of :class:`iagent_mesh.results.MeshResult`, never a value carried inside it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: WriteOutcome
    detail: Optional[str] = None
    """Why, for anything short of a clean ``written``. Required on every state but ``written`` —
    a degrade, a refusal, or a failure with no reason reaches an operator as "something happened"
    and is exactly how the read side's silent failures went unnoticed for sixty-seven days."""

    @field_validator("detail")
    @classmethod
    def _detail_not_blank_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("detail='' — omit the field rather than stating nothing")
        return v

    @model_validator(mode="after")
    def _states_are_coherent(self) -> "MeshWriteResult":
        if self.outcome != "written" and not (self.detail or "").strip():
            raise ValueError(
                f"outcome={self.outcome!r} with no detail — anything but a clean 'written' must "
                f"say why, the same discipline MeshResult applies to its own failure states"
            )
        return self

    # ── constructors, so the coherent cases are the short ones ───────────────────────────

    @classmethod
    def written(cls) -> "MeshWriteResult":
        """Landed, vector included wherever one is required. Nothing left to explain."""
        return cls(outcome="written")

    @classmethod
    def written_without_vector(cls, detail: str) -> "MeshWriteResult":
        """Landed WITHOUT a vector. Reachable only when the caller opted in with
        ``vector_required=False`` — ``detail`` names why no vector was attached, because a
        vectorless write with no explanation is indistinguishable from one nobody noticed."""
        return cls(outcome="written_without_vector", detail=detail)

    @classmethod
    def refused(cls, detail: str) -> "MeshWriteResult":
        """Declined before touching the store — an identity gate, or a caller input the writer
        will not act on (an embed failure with no ``vector_required=False`` waiver, an empty
        write, an unscoped write request)."""
        return cls(outcome="refused", detail=detail)

    @classmethod
    def failed(cls, detail: str) -> "MeshWriteResult":
        """Asked; the store refused or errored."""
        return cls(outcome="failed", detail=detail)

    @classmethod
    def unreachable(cls, detail: str) -> "MeshWriteResult":
        """COULD NOT ASK. Separate from ``failed`` because the remedy is a deployment one."""
        return cls(outcome="unreachable", detail=detail)

    # ── reading it ───────────────────────────────────────────────────────────────────────

    @property
    def applied(self) -> bool:
        """True for BOTH landed states — ``written`` and ``written_without_vector``. Named
        rather than given to ``bool()``, same reasoning as ``MeshResult.answered_ok``: a reader
        of ``if r.applied`` can see which question is being asked, where ``if r`` cannot."""
        return self.outcome in ("written", "written_without_vector")

    def require(self, what: str = "write") -> "MeshWriteResult":
        """This result, or raise naming the outcome. The safe one-liner, so nobody writes the
        unsafe one. A caller that also needs to know whether a vector landed still has
        ``.outcome`` — ``require()`` only guarantees the write applied, not which flavour."""
        if not self.applied:
            raise WriteNotApplied(
                f"{what} did not apply: outcome={self.outcome!r} detail={self.detail!r}"
            )
        return self

    def __bool__(self) -> bool:  # noqa: D105 — the docstring is the module's
        raise AmbiguousWriteResultTruth(
            f"MeshWriteResult has no truth value (outcome={self.outcome!r}). `if result:` would "
            f"collapse refused, failed and unreachable into one branch, and fold "
            f"written_without_vector into the same truthy branch as written — hiding the one "
            f"state this vocabulary exists to keep visible. Use `result.outcome`, "
            f"`result.applied`, or `result.require()`."
        )
