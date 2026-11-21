"""``PagedAnswer`` — the one envelope for all nine ``mesh:mfg*`` verbs, ADR-0070 section 3
(invincible-agent PR #379, merged 2026-11-15; its five open questions ruled by the architect
2026-11-14, section 10 — the ADR itself stays "Proposed", not ratified).

The ADR's own words: *"One envelope means one reader in cortex... If the SDK has no typed paged
answer of this shape, ca adds it, with the TS mirror (the dispatch's 'only if needed' item;
cortex says it is needed)."* This module is that addition. The envelope, verbatim from section 3:

    { rows: [...],                # each row: its fields + citation {source, record_id, extracted_at}
      next: <opaque cursor|null>, # passed back verbatim
      rollup: {...} | null,       # register and tests only
      reason: null | no_data | not_visible | excluded_part | source_stale,
      withheld: {...} | null,     # section 4
      suppressed: [{statistic, reason}],   # stats only
      downsampled: {from_n, to_n} | null,  # series only
      provenance: {dataset_urn, as_of, as_of_unavailable, as_of_source, ticket_id, issued_at} }

Searched first for a reusable fit, same discipline :class:`iagent_mesh.lifecycle_status.DataProvenance`
states for itself: :class:`iagent_mesh.results.MeshResult` is a three-state substrate-outcome
contract (ok/failed/pending), not a paging envelope, and its generic row slot is a single value, not
a page; :class:`iagent_mesh.provenance.EvidenceRef` is a document-extraction citation, a different
concept from :class:`RowCitation` below even though both name a source. Neither fits; this module
mints the shapes the ADR's envelope needs.

**TS MIRROR IS OUT OF THIS MODULE'S SCOPE.** ``cortex-ui/src/api/generated/bff.ts`` is generated
("DO NOT EDIT — run npm run gen:api") from invincible-agent's own OpenAPI document — it is not a
file ca hand-writes. The mirror exists once ``lane/mt`` (ADR-0070 section 7, not yet built) types
its ``POST /mfg/{verb}`` BFF route against this module's shape; ca's own scope is this Python type.

**REFUSALS ARE OUT OF THIS MODULE'S SCOPE.** Section 3: "a contract refusal is a refusal, never a
200." A refused request never reaches a :class:`PagedAnswer` at all — it goes through
:mod:`iagent_mesh.refusal`'s pre-existing ``Refusal``/``PartialRefusal`` shapes instead. ``reason``
on this envelope is the OK-with-nothing-to-show case ("empty is not an error. It is a 200 with a
`reason` code" — section 3), never a denial.

**``reason``/``withheld`` STAY OPEN, per generic-at-birth.** Section 3 names
``no_data``/``not_visible``/``excluded_part``/``source_stale`` as the reason vocabulary and section
4 gives ``withheld``'s shape for two of the nine verbs (``children_withheld``/``parent_withheld``)
— but both are served, deployment-shaped data (``GET /mfg/declarations`` serves the empty-reason
codes; ``withheld``'s exact keys vary per verb, e.g. ``mesh:containment``'s per-level naming versus
``mesh:unitGenealogy``'s per-row boolean), the same posture :attr:`iagent_mesh.lifecycle_status.
LifecycleStatus.status` already takes against its own served vocabulary file. Neither is a
``Literal`` or a closed schema here.

**``as_of``: ``None`` means absent; ``as_of_unavailable`` says why (0.9.27).** Section 5:
"``AS_OF_READERS`` ships empty for ClickHouse... every answer carries ``as_of_unavailable``. That
is honest, and it is not a refusal." 0.9.22 read that as a literal sentinel string the ADR wanted
on ``as_of`` itself and deliberately diverged from it, in favor of this SDK's own ``None``-means-
absent convention. That divergence quietly reopened the exact gap the ADR's sentinel existed to
close: a caller that never set ``as_of`` at all and one that read its source and found no as-of
both produced the identical ``as_of=None`` — cortex's own finding, from the mfg navigator's
pre-build design pass (``sessions/2026-11-20-plan-...-the-mfg-navigator-plan.md`` §6 Q12) against
the architect's 11-20 ruling: "when an as-of is unavailable, say so; never show a blank or a stale
date as current." 0.9.27 resolves it the SDK's own way rather than adopting the ADR's sentinel
string after all: ``as_of`` stays a required-but-nullable key (``None`` is still the absence
marker, and is now REQUIRED rather than defaulted, so a caller must say ``as_of=None`` rather than
omit the key — the same "stated, never defaulted" discipline as :class:`iagent_mesh.
lifecycle_status.DataProvenance.as_of`), and a new, equally required-when-needed
``as_of_unavailable`` carries the *reason*, enforced by a cross-field check: ``as_of=None`` with
``as_of_unavailable=None`` is refused — a blank with no reason is exactly what "say so" forbids.
``as_of_source`` (new, also 0.9.27) is the lesser sibling fact for a *present* ``as_of``: where it
came from (fin's receipt distinguishes ``read_at_authorize`` from ``advertised_at_load``), open
the same way.
"""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "RowCitation",
    "SuppressedStatistic",
    "Downsample",
    "AnswerProvenance",
    "PagedAnswer",
]

T = TypeVar("T")


class RowCitation(BaseModel):
    """``{source, record_id, extracted_at}`` — section 3: "each row: its fields + citation." Every
    row of every one of the nine ``mesh:mfg*`` verbs carries one of these; this module does not
    carry the row's own fields, which are per-verb and belong to whichever caller defines that
    verb's row shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    """Which served table the row came from, e.g. ``serial_unit`` or ``test_result`` (section 3's
    own ``reads`` column names the per-verb vocabulary; this field carries whichever name a
    deployment's own verb implementation used, never validated against a closed list here)."""
    record_id: str
    """The row's identity within ``source``, opaque to this model."""
    extracted_at: str
    """ISO-8601, this SDK's house convention for a wire timestamp — never ``datetime``."""

    @field_validator("source", "record_id", "extracted_at")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"RowCitation.{info.field_name}='' — required; a citation that cannot say "
                f"which table, which row, or when is not a citation anyone downstream can "
                f"verify"
            )
        return v


class SuppressedStatistic(BaseModel):
    """``{statistic, reason}`` — section 3: "each suppressed statistic named, with the reason,"
    carried on ``mesh:measurementStats``'s envelope (e.g. ``Cpk`` suppressed because a limit is
    non-numeric). Stats-only, per the envelope comment; other verbs leave
    :attr:`PagedAnswer.suppressed` empty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statistic: str
    """Which statistic was suppressed, e.g. ``"Cpk"``."""
    reason: str
    """Why — opaque to this model, the same posture :class:`iagent_mesh.refusal.Refusal` takes on
    its own ``missing_binding``."""

    @field_validator("statistic", "reason")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"SuppressedStatistic.{info.field_name}='' — a suppressed statistic with no name "
                f"or no reason is not distinguishable from one that was never computed"
            )
        return v


class Downsample(BaseModel):
    """``{from_n, to_n}`` — section 3: "server-side downsampling above ``max_points``," carried on
    ``mesh:measurementSeries``'s envelope. Series-only, per the envelope comment; other verbs leave
    :attr:`PagedAnswer.downsampled` ``None``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_n: int
    """How many points the series held before downsampling."""
    to_n: int
    """How many points were actually served, after downsampling. Section 3: the server "always
    keeps the highlighted, out-of-limit and out-of-family points" — this model does not check
    which points, only the counts."""

    @model_validator(mode="after")
    def _to_n_does_not_exceed_from_n(self) -> "Downsample":
        if self.from_n < 0 or self.to_n < 0:
            raise ValueError(
                f"Downsample(from_n={self.from_n}, to_n={self.to_n}) — neither count can be "
                f"negative"
            )
        if self.to_n > self.from_n:
            raise ValueError(
                f"Downsample(from_n={self.from_n}, to_n={self.to_n}) — downsampling cannot "
                f"increase the point count; a series serving more points than it started with "
                f"was not downsampled"
            )
        return self


class AnswerProvenance(BaseModel):
    """``{dataset_urn, as_of, ticket_id, issued_at}`` — section 3's envelope-level ``provenance``,
    section 5: "every answer's ``provenance`` comes from the broker ticket, as fin's does."

    A NEW model, not a reuse of :class:`iagent_mesh.lifecycle_status.DataProvenance` — searched
    first (this module's own discipline, stated above): the field sets differ. This envelope
    needs :attr:`issued_at` (when the broker ticket itself was issued, section 5), which
    ``DataProvenance`` has no equivalent of; ``DataProvenance`` is a per-row-input triple attached
    to one :class:`iagent_mesh.lifecycle_status.ImpactRow`, this is a per-answer, envelope-level
    fact. Shared names (``dataset_urn``, ``as_of``, ``ticket_id``), different shapes, different
    owners — not the same type wearing two hats.

    Unlike ``DataProvenance``, :attr:`issued_at` is the one field this model requires
    unconditionally: section 3's envelope marks ``provenance`` itself as the only field with no
    ``| null`` in the whole shape, and an answer's ticket is always issued at some moment even when
    the dataset it names or the ``as_of`` it could compute are unavailable (section 5's ClickHouse
    gap)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_urn: Optional[str] = None
    """``None`` means absent — no catalogue entry — never a placeholder string, same convention as
    :attr:`iagent_mesh.lifecycle_status.DataProvenance.dataset_urn`."""
    as_of: Optional[str]
    """ISO-8601, or ``None`` when no as-of was read. REQUIRED (no default): a caller states
    absence with ``as_of=None`` rather than omitting the key, so absence is a stated fact, never a
    silently-defaulted one — the same discipline :attr:`iagent_mesh.lifecycle_status.
    DataProvenance.as_of` already takes, applied here because a missing key and an explicitly
    ``None`` one were otherwise indistinguishable, which is exactly the gap cortex found: a
    ``PagedAnswer`` whose caller never set this at all read identically to one that read the
    source and found no as-of. ADDED (required, no default) 0.9.27.

    The architect's 11-20 ruling: "when an as-of is unavailable, say so; never show a blank or a
    stale date as current." ``None`` here is the "say so" — paired with :attr:`as_of_unavailable`
    below, which carries *why*, since ``None`` alone does not say anything a UI could draw."""
    as_of_unavailable: Optional[str] = None
    """Why :attr:`as_of` is ``None`` — required whenever it is (see the cross-field check below),
    ``None`` when :attr:`as_of` is present. An open string, not a ``Literal``, per generic-at-birth:
    fin's broker reports one of four of its own constants (``no_reader_for_source_type``,
    ``reader_declined``, ``reader_failed``, ``reader_returned_unusable_value``, PR #496) and a
    different domain's broker will report its own vocabulary — the same served-vocabulary posture
    :attr:`iagent_mesh.lifecycle_status.LifecycleStatus.status` and
    :class:`iagent_mesh.paged_answer.PagedAnswer`'s own :attr:`~PagedAnswer.reason` already take.
    ADDED 0.9.27."""
    as_of_source: Optional[str] = None
    """Where a *present* :attr:`as_of` came from, when that matters to the reader — fin's receipt
    names ``read_at_authorize`` (read fresh for this ticket) versus ``advertised_at_load`` (the
    source's own claimed timestamp, not re-read for this ticket); carried here under the same
    names, open string for the same reason as :attr:`as_of_unavailable`. ``None`` means not
    stated, which is not the same claim as ``read_at_authorize`` — a caller that knows which one
    it is should say so, not default silently. ADDED 0.9.27."""
    ticket_id: Optional[str] = None
    """``None`` means absent — no broker read — never a placeholder string, same convention as
    :attr:`iagent_mesh.lifecycle_status.DataProvenance.ticket_id`."""
    issued_at: str
    """ISO-8601. When the broker ticket this answer's provenance comes from was issued. Required —
    see the class docstring: this is the one envelope field the ADR never marks nullable."""

    @field_validator("dataset_urn", "as_of", "as_of_unavailable", "as_of_source", "ticket_id",
                      "issued_at")
    @classmethod
    def _optional_field_is_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                f"AnswerProvenance.{info.field_name}='' — use None for absent, not a blank string"
            )
        return v

    @model_validator(mode="after")
    def _as_of_unavailable_says_so_exactly_when_as_of_is_absent(self) -> "AnswerProvenance":
        if self.as_of is None and self.as_of_unavailable is None:
            raise ValueError(
                "AnswerProvenance.as_of=None with as_of_unavailable=None — the 11-20 ruling is "
                "'when an as-of is unavailable, say so'; an absent as_of with no stated reason is "
                "exactly the blank this field exists to forbid. Pass a reason, even an opaque one."
            )
        if self.as_of is not None and self.as_of_unavailable is not None:
            raise ValueError(
                f"AnswerProvenance.as_of={self.as_of!r} is present, but "
                f"as_of_unavailable={self.as_of_unavailable!r} is also set — a reason explains an "
                f"absence, it does not ride alongside a served value"
            )
        return self


class PagedAnswer(BaseModel, Generic[T]):
    """The one envelope for all nine ``mesh:mfg*`` verbs — ADR-0070 section 3. See the module
    docstring for the envelope's verbatim shape, scope boundaries (no refusals, no hand-written TS
    mirror), and the ``reason``/``withheld``/``as_of`` design notes.

    Fields are in the envelope's own order. ``rows`` is generic over the per-verb row type
    (:class:`RowCitation` is each row's citation, not its fields — see :class:`RowCitation`'s own
    docstring); this module does not define any verb's row shape, the same split
    :mod:`iagent_mesh.lifecycle_status`'s module docstring draws between shipping row shapes and
    shipping the emitter that fills them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[T, ...] = ()
    """The page's rows, in whatever per-verb shape the caller's ``T`` names. Empty is not an
    error — section 3: "empty is not an error. It is a 200 with a `reason` code" — see
    :attr:`reason`."""
    next: Optional[str] = None
    """An opaque cursor, passed back verbatim on the next call. ``None`` means no further page.
    Never parsed or constructed by this model — section 3: "``next: <opaque cursor|null>`` passed
    back verbatim.\""""
    rollup: Optional[dict[str, Any]] = None
    """Register and tests only (section 3's envelope comment); other verbs leave this ``None``.
    Shape is per-verb (e.g. ``mesh:asBuiltRegister``'s "counts by status for the filtered set") and
    not modeled further here, the same open-dict posture as :attr:`withheld`."""
    reason: Optional[str] = None
    """``None``, or one of the empty-reason codes ``GET /mfg/declarations`` serves (section 3's own
    four examples: ``no_data``, ``not_visible``, ``excluded_part``, ``source_stale``) — an open
    string, not a ``Literal``, per generic-at-birth: the real vocabulary is deployment-served, the
    same posture :attr:`iagent_mesh.lifecycle_status.LifecycleStatus.status` takes against its own
    served registry file. This is the OK-with-nothing-to-show case, never a refusal — see the
    module docstring."""
    withheld: Optional[dict[str, Any]] = None
    """Section 4's visibility disclosure. Shape varies per verb — e.g. ``mesh:containment``'s
    envelope-level per-level naming versus ``mesh:unitGenealogy``'s per-row
    ``children_withheld``/``parent_withheld`` booleans (which live on the row, not here, for that
    verb) — so this field is an open dict, not a fixed schema, the same reasoning as
    :attr:`rollup`."""
    suppressed: tuple[SuppressedStatistic, ...] = ()
    """``mesh:measurementStats`` only (section 3's envelope comment); other verbs leave this
    empty."""
    downsampled: Optional[Downsample] = None
    """``mesh:measurementSeries`` only (section 3's envelope comment); other verbs leave this
    ``None``."""
    provenance: AnswerProvenance
    """Required — the envelope's own only non-nullable field (section 3). See
    :class:`AnswerProvenance`'s docstring."""
