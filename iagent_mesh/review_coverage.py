"""The SDK-side type for the review-coverage record, per the architect's 2026-10-30 ruling (the
same ruling that reopened ``ContentKindRegistration.review_shape`` to a registry-validated string
— see ``iagent_mesh/ingest.py``): "``review_coverage`` is generic review provenance, not a PCN
field... The type goes into the SDK (ca, v0.9.12) as ``ReviewCoverage`` and the BFF imports it."
Stored on the provenance record of the promotion/approval, never on the workflow — a different
write path from both the graph-assertion provenance :mod:`iagent_mesh.provenance` carries in the
same write, and the four unwired ADR-0060 shapes :mod:`iagent_mesh.persistence` carries; this
module is neither of those, it is a separate, wired/populated ruling.

Typed exactly per Lane 1's (invincible-agent) wire-answer packet to cortex-ui, answering cortex's
five earlier blocking questions on the ``review_coverage`` rename —
``sessions/2026-10-30-packet-to-cortex-cc-ca-from-lane-01-five-answers-review-coverage-0-4-73-wire.md``
in this repo. Cortex-ui is the eventual wire producer of a ``ReviewCoverage`` record; the BFF
(``invincible-agent``, 0.4.73) imports this type so "ca types it, the BFF imports it" (the wire
packet's own ``Order``, item 1-2) resolves to one shape from one import path, same reason
:mod:`iagent_mesh.provenance` and :mod:`iagent_mesh.refusal` are re-exported at the package root.

``groups[].rule`` and ``shared[].rule`` are plain, registry-sourced ``str`` ids (e.g.
``"same_shape_run"``, ``"same_inherited_crop"``) — NOT a closed enum. The wire packet's §4 draws
the split explicitly: "a rule id names a mechanism that [the consumer] implements... Config:
which rules apply to a shape, and with what parameters." A new rule is a
``policy/review_shapes/<shape>.yaml`` registry row (code + config), not an SDK release, per the
generic-at-birth standing rule (no new wire value this SDK carries hard-codes a closed set that a
registry row should instead widen).

This module does not serve, cache, or validate the ``policy/review_shapes/`` registry itself —
``GET /review-shapes`` and the registry files are the BFF's own deliverables (the wire packet's
"Fixed by the architect" section). ``ReviewShapeRow`` only types the shape a client deserializes a
served row INTO, the same split every registry-adjacent type in this SDK draws between declaring
a shape and arbitrating on it.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "ReviewCoverageGroup",
    "ReviewCoverageSharedFact",
    "ReviewCoverage",
    "ReviewShapeRule",
    "ReviewShapeRow",
]


class ReviewCoverageGroup(BaseModel):
    """One grouping a review-coverage rule produced — e.g. a run of items the ``same_shape_run``
    rule clustered together. ``parts`` -> ``items``, per the 2026-10-30 rename ruling (the wire
    packet's §1 field list): the field holds item ids, not the old integer ``part_index`` values.
    """

    rule: str
    """The grouping rule's registry id, e.g. ``"same_shape_run"`` — a plain, registry-sourced
    string, not a closed enum (see the module docstring). The server refuses a ``rule`` not
    present in the shape row's own ``rules`` list (``review_coverage_invalid``, key
    ``unknown_rule``, per the wire packet's §4); this type does not pre-validate that, the same
    split every registry-adjacent type in this SDK draws."""

    key: str
    """The grouping key within that rule — e.g. a shared crop signature, an inherited-crop id.
    Opaque to this type: the rule, not ``ReviewCoverageGroup``, defines what a ``key`` means, so
    no format or vocabulary is imposed here."""

    items: list[str] = Field(default_factory=list)
    """Item ids this group covers (see :attr:`ReviewCoverage.looked_at` for the id convention —
    a decimal string for the ``notice`` shape's ``part_index``, a shape-defined string for every
    other shape). ``parts`` -> ``items``, per the 2026-10-30 rename ruling."""


class ReviewCoverageSharedFact(BaseModel):
    """One fact (e.g. a shared crop/region) spanning multiple items, confirmed or not. ``page``/
    ``bbox`` follow the SAME page-fraction, top-left-origin, 0..1 convention as
    :attr:`iagent_mesh.provenance.EvidenceRef.bbox` — one bbox convention everywhere this SDK
    carries one, per the 2026-10-21 ruling that already governs ``EvidenceRef``. Unlike
    ``EvidenceRef.bbox``, this ``bbox`` is required, not ``Optional``: a shared fact is always
    reported against a drawn region, never a page-only citation with no box."""

    rule: str
    """The shared-fact rule's registry id, e.g. ``"same_inherited_crop"`` — same registry-sourced,
    open-vocabulary convention as :attr:`ReviewCoverageGroup.rule`."""

    page: int
    """1-indexed page number, same convention as :attr:`iagent_mesh.provenance.EvidenceRef.page`
    — not 0-indexed, which would require every consumer to add 1 before rendering a citation."""

    bbox: tuple[float, float, float, float]
    """``(x0, y0, x1, y1)``, each a fraction of the page in ``0..1``, origin TOP-LEFT — identical
    convention and validation to :attr:`iagent_mesh.provenance.EvidenceRef.bbox` (see its
    ``_bbox_is_well_formed`` validator and the 2026-10-21 ruling it implements), reused here
    rather than re-derived so one bbox convention holds everywhere this SDK carries one."""

    items: list[str] = Field(default_factory=list)
    """Item ids this shared fact spans. ``parts`` -> ``items``, same rename as
    :attr:`ReviewCoverageGroup.items`."""

    confirmed: bool
    """Whether a reviewer has confirmed this shared fact, as distinct from it merely having been
    detected and reported. No default: the wire packet's §1 field list gives this field no
    default either, and a sender that has not decided confirmed-or-not should not be able to omit
    the question."""

    @field_validator("bbox")
    @classmethod
    def _bbox_is_well_formed(
        cls, v: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        # The non-Optional twin of EvidenceRef._bbox_is_well_formed (iagent_mesh/provenance.py):
        # same 0..1 page-fraction range check and the same positive-area check, minus the `None`
        # short-circuit EvidenceRef needs and this field does not (bbox is required here).
        x0, y0, x1, y1 = v
        if not all(0.0 <= c <= 1.0 for c in v):
            raise ValueError(
                f"ReviewCoverageSharedFact.bbox={v!r} — every coordinate is a page fraction in "
                f"0..1 (the 2026-10-21 ruling EvidenceRef.bbox already follows); a value outside "
                f"that range is unconverted pixel/point geometry, not a citation this type "
                f"accepts"
            )
        if not (x1 > x0 and y1 > y0):
            raise ValueError(
                f"ReviewCoverageSharedFact.bbox={v!r} — (x1, y1) must be strictly greater than "
                f"(x0, y0), or the box has zero or negative area and cites nothing"
            )
        return v


class ReviewCoverage(BaseModel):
    """One review-coverage record: what a reviewer looked at, sampled, flagged, and grouped,
    against the shape and rules version it was computed with. Stored on the provenance record of
    a promotion/approval (see the module docstring); this type does not itself write or validate
    against anything — the server validates ``review_shape``/``item_kind``/``rules_version``
    against the ``policy/review_shapes/`` registry (the wire packet's §3/§4), this type only
    carries the fields the wire packet's §1 field list names."""

    review_shape: str
    """Required. The drop's kind's declared review shape (e.g. ``"notice"``) — same open-string
    field as ``ContentKindRegistration.review_shape`` (``iagent_mesh/ingest.py``), now reopened to
    a registry-validated string by the same 2026-10-30 ruling. The SERVER validates this against
    the ``policy/review_shapes/`` registry; this type does not re-validate it."""

    item_kind: str
    """Required, ONCE at the top level (not per group) — one shape has one item kind, per Lane
    1's wire answer. Must equal the shape row's declared ``item_kind`` (``ReviewShapeRow`` below);
    enforcement is the server's, not this type's."""

    rules_version: str
    """The rules version the client computed this record's groups with — now sourced from the
    shape row (``ReviewShapeRow.rules_version``) rather than a client constant. The server
    refuses a new-form record whose ``rules_version`` is not that shape's current row
    (``review_coverage_invalid``, key ``unknown_rules_version``, per the wire packet's §4): a
    grouping computed with stale parameters is refused, not recorded."""

    looked_at: list[str] = Field(default_factory=list)
    """Item ids. Kept its name across the ``parts`` -> ``items`` rename: "a verb about items, not
    a domain noun" (Lane 1's wire answer, §1)."""

    sampled: list[str] = Field(default_factory=list)
    """Item ids. Same naming rationale as :attr:`looked_at`."""

    flagged: list[str] = Field(default_factory=list)
    """Item ids. Same naming rationale as :attr:`looked_at`."""

    groups: list[ReviewCoverageGroup] = Field(default_factory=list)
    """This record's groupings, one entry per rule-produced cluster. ``parts`` -> ``items``, per
    the 2026-10-30 rename ruling — see :class:`ReviewCoverageGroup`."""

    shared: list[ReviewCoverageSharedFact] = Field(default_factory=list)
    """This record's shared facts (e.g. shared crops/regions spanning multiple items).
    ``parts`` -> ``items``, same rename — see :class:`ReviewCoverageSharedFact`."""

    sample: Optional[dict[str, Any]] = None
    """Opaque: "stays; recorded as sent" (Lane 1's wire answer, §1) — this type does not impose a
    schema on the sampling-strategy object; the shape row (``ReviewShapeRow.params``) is where
    sample PARAMETERS are now declared as config, this field only records what a given send
    carried."""


class ReviewShapeRule(BaseModel):
    """One rule a review-shape row admits — a MECHANISM id cortex (or any consumer) implements,
    with config-carried parameters. "A rule id names a mechanism that [the consumer] implements
    ... Config: which rules apply to a shape, and with what parameters" (Lane 1's wire answer,
    §4)."""

    id: str
    """The rule's registry id, e.g. ``"same_shape_run"`` — matches ``ReviewCoverageGroup.rule`` /
    ``ReviewCoverageSharedFact.rule`` when a client applies this rule. Open string: a new rule is
    a registry row naming a mechanism the consumer already implements, not an SDK release."""

    params: dict[str, Any] = Field(default_factory=dict)
    """This rule's parameters as declared by the shape row, e.g. ``{"min_run": 3, "per_run": 2}``
    for ``same_shape_run`` (the wire packet's §4 example). Moves what was a client constant
    (cortex's own ``min_run``/``per_run``) into config the row carries, per the wire packet's
    split: "Your constants ... move out of cortex into the row.\""""


class ReviewShapeRow(BaseModel):
    """One ``policy/review_shapes/<shape>.yaml`` registry row, as served by ``GET /review-shapes``
    (Lane 1's wire answer, §4) — the registry ``ReviewCoverage.review_shape``/``.item_kind`` are
    validated against, server-side. This SDK types the row so a client that reads the served
    registry has a shape to deserialize into; it does not serve, cache, or validate against the
    registry itself — same split every registry-adjacent type in this SDK draws between declaring
    a shape and arbitrating on it."""

    review_shape: str
    """The shape this row describes, e.g. ``"notice"``, ``"document"``, ``"course"``,
    ``"finding"`` — the four shapes the wire packet's §4 names as seeded (``notice`` plus the
    three seeded with ``rules: []`` until a rule is declared for them)."""

    item_kind: str
    """The item kind this shape's reviews address, e.g. ``"part"`` for ``notice``. Must match
    what ``ReviewCoverage.item_kind`` carries for a record of this shape; enforcement is the
    server's."""

    rules_version: str
    """This row's current rules version, e.g. ``"notice.v1"``. A ``ReviewCoverage`` record
    computed against a stale version is refused (``unknown_rules_version``, per the wire packet's
    §4), so a client reads this field to know what to compute against and to send back."""

    params: dict[str, Any] = Field(default_factory=dict)
    """Row-level parameters not scoped to a single rule, e.g. ``{"sample_all_up_to": 4}`` for
    ``notice`` (the wire packet's §4 example). Lane 1 flags this split as theirs to correct, not
    cortex's: "I read ``per_run 2`` as belonging to ``same_shape_run``, and ``sample_all_up_to 4``
    as row-level. You wrote those constants, so if either is wrong, say so and the seed follows
    you" — this type carries whichever split the row ends up declaring, it does not itself take a
    position on which constant belongs where."""

    rules: list[ReviewShapeRule] = Field(default_factory=list)
    """The rules this shape admits. ``[]`` for a seeded-but-undeclared shape (``document``,
    ``course``, ``finding``, per the wire packet's §4) "until someone declares a rule for them" —
    an empty list is a real, valid row state, not an omission."""
