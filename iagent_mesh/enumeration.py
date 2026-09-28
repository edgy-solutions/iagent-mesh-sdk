"""The `mesh:enumerateInstances` contract: what a caller asks, and what the answer CLAIMS.

One shape, because there were FIVE. Measured 2026-09-17 across the fleet, by AST rather than by
reading — the classes live at different line counts and a fixed window truncates them:

    cost_agent         EnumerateRequest           class_uri (req), limit = 25
    finance_agent      EnumerateRequest           class_uri (req), limit = 8
    ontology_service   EnumerateInstancesRequest  class_uri (req)
    planning_agent     EnumerateInstancesRequest  class_uri = ''        <- OPTIONAL
    safety_agent       EnumerateRequest           class_uri (req), limit = 25

TWO OF THOSE DIVERGENCES CHANGE BEHAVIOUR, not style:

  * **THE MENU'S SIZE DEPENDS ON WHO ANSWERS.** A caller that omits `limit` gets 25 options from
    cost and safety, 8 from finance, and everything from ontology and planning. The ask builder
    draws a menu without knowing which of those it received, so "the options" is a different set
    per provider for the same question.
  * **`class_uri` IS OPTIONAL IN ONE PROVIDER.** Enumerating with no class succeeds against
    planning and 422s against the other four — so the same malformed request is a refusal from
    four engines and an answer from one, and nothing reports which happened.

── THE THREE STATES OF AN ENUMERATION, AND WHY `scoped_by` AND `completeness` ARE FIELDS ────
RULED 2026-09-16 (scoping) and 2026-09-23 (limit — the same ruling, extended). A provider may be
handed bound slots as scoping context, and asked for at most `limit` instances; the response must
say whether it USED the context and whether it delivered the WHOLE menu.

    scoped_by: ["lot"]   the provider honoured the bound slots — this list is lot-scoped
    scoped_by: []        it answered CLASS-WIDE, whatever it was given
    (no response)        no enumeration happened — no provider, or a refusal

**NEVER A CLASS-WIDE LIST WEARING A SCOPED MENU.** `cost#RateTable` enumerates to 12 while lot 3
accepts 2. Wiring a bound slot to the class-scoped door would build a menu where ten options
produce the refusal the menu exists to prevent — the user picks, and the pick is rejected. So a
provider that ignores context it was given answers honestly as class-wide, and the ask builder
refuses to draw a scoped menu from a class-wide list.

`scoped_by` DEFAULTS TO `[]`, AND THE DEFAULT IS THE FAIL-SAFE DIRECTION. A provider that honours
the slots but forgets the field is reported as class-wide, so the menu is refused — it
under-claims. The opposite default would make a forgetful provider's class-wide list look scoped,
which is the exact defect. This is the only asymmetry in the model and it is deliberate.

**THE SAME RULE APPLIES TO `limit`, AND NOW IT IS IMPLEMENTED.** A truncated list wearing a
complete menu is the same defect as a class-wide list wearing a scoped one: the caller cannot
tell "these are the options" from "these are the first 25 of them", and a menu that silently
omits the user's answer is worse than a refusal. `completeness` names three states the same shape
as scoping:

    completeness: "complete"     the provider claims `instances` is the whole population
    completeness: "truncated"    the provider claims more exist beyond `instances`
    completeness: "unknown"      the provider has not said either way

`completeness` DEFAULTS TO `"unknown"`, AND THE DEFAULT IS THE SAME FAIL-SAFE DIRECTION AS
`scoped_by`'S DEFAULT OF `[]`. A provider that has not been migrated to this field (0 of 5
providers currently emit it — see the table above) must not be read as either "complete" or
"truncated": `"unknown"` is an honest under-claim, not a guess collapsed into `"complete"`. This
field is a CLAIM the provider makes, never something this module DERIVES from
`len(instances) < limit` — inferring completeness from the count is exactly the shape this
docstring warns against for `scoped_by`, in the other direction: there, a name that was NOT
claimed is the defect; here, a completeness that was not claimed would be the defect.
`total_available`, when a provider knows the population size, says how far short
`instances` falls; `None` means "not knowable or not reported", not zero. :func:`over_limit` is
the seal on the one thing this module CAN check without trusting a claim: the invariant
`len(instances) <= limit` itself.

── WHAT THIS MODULE DOES NOT DO ────────────────────────────────────────────────────────────
It does not make anything call an enumerate. `src/iagent/defs/dynamic_supervisor.py` records that
Engine P is a REGISTERED provider with no router-side fan-out — "a registration is not a reachable
call" — so the disposition runs with no enumerator and reports `free_text_reason: no_provider`.
Binding this shape is the contract half; the fan-out is a separate act by a separate lane.
"""
from __future__ import annotations

from typing import Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "DEFAULT_ENUMERATE_LIMIT",
    "unhonoured_scoping",
    "over_limit",
    "EnumerateInstancesRequest",
    "EnumerateInstancesResponse",
    "InstanceOption",
]

#: ONE default, and adopting it CHANGES finance_agent from 8 to 25. That is a deliberate,
#: recorded consequence rather than a silent one: three providers already use 25 and two use no
#: limit at all, so any single value changes somebody. A model that kept every provider's current
#: default would be the five shapes again with extra steps.
DEFAULT_ENUMERATE_LIMIT = 25


class InstanceOption(BaseModel):
    """One member of a class, as a menu entry.

    `uri` is the identity and `label` is what a person reads. Both, because a menu showing URIs
    is unusable and a menu showing labels alone cannot round-trip the pick.
    """

    model_config = ConfigDict(extra="forbid")

    uri: str
    label: str


class EnumerateInstancesRequest(BaseModel):
    """What a caller asks an enumerate provider.

    `extra="forbid"` ON PURPOSE. A provider that silently ignores a field it does not understand
    is how `limit` came to mean three different things — the caller sent it, one engine honoured
    it, and nothing said so. A rejected unknown field is a fixable error; an ignored one is a
    wrong answer.
    """

    model_config = ConfigDict(extra="forbid")

    class_uri: str
    """REQUIRED AND NON-EMPTY, which resolves the divergence toward the stricter four providers.
    `class_uri = ''` means "enumerate what?" and has no answer — planning_agent accepting it made
    the same malformed request a refusal from four engines and an answer from one."""

    bound_slots: dict[str, str] = {}
    """Slots already bound in this turn, as scoping CONTEXT — `{"lot": "3"}`.

    A provider MAY use these to narrow the enumeration and MUST report whether it did, via
    `scoped_by` on the response. Passing context is not a demand: a provider that cannot scope
    answers class-wide and says so.
    """

    limit: int = DEFAULT_ENUMERATE_LIMIT

    @field_validator("class_uri")
    @classmethod
    def _class_uri_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "class_uri is required and must be non-empty: an enumeration with no class has "
                "nothing to enumerate. This is the divergence one provider accepted as ''."
            )
        return v

    @field_validator("limit")
    @classmethod
    def _limit_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("limit must be at least 1; a limit of 0 is a refusal, not a menu")
        return v


class EnumerateInstancesResponse(BaseModel):
    """What the provider answers, INCLUDING WHAT IT CLAIMS ABOUT ITS OWN ANSWER."""

    model_config = ConfigDict(extra="forbid")

    instances: Sequence[InstanceOption] = ()

    scoped_by: Sequence[str] = ()
    """WHICH bound slots the provider actually applied. Empty means CLASS-WIDE.

    Reported as the slot NAMES rather than a boolean, because "scoped" is not one state: a
    provider handed `{"lot", "category"}` that honours only `lot` has produced a list scoped by
    one of two, and a boolean would let the ask builder believe both were applied.

    THE INVARIANT, AND IT IS THE OTHER HALF OF
    :attr:`iagent_mesh.graph_manifest.SlotDecl.narrowed_by`:

        scoped_by  <=  narrowed_by  &  bound

    This list is DRAWN FROM the slot's `narrowed_by` — the row's declaration of which dimensions
    restrict it — intersected with what is actually bound this turn. That side is the
    OBLIGATION, stated once at ratification; this side is the CLAIM about one answer. A declared
    name missing here is a narrowing the provider did not apply, and the menu is refused;
    :func:`unhonoured_scoping` is the comparison. A name here that the row never declared is out
    of the invariant the other way — a provider claiming a scoping nobody asked for, which is a
    provider defect rather than a row one, and it does not make a menu safe to draw.
    """

    @field_validator("scoped_by")
    @classmethod
    def _no_blank_slot_names(cls, v: Sequence[str]) -> Sequence[str]:
        if any(not s or not s.strip() for s in v):
            raise ValueError(
                "scoped_by carries a blank slot name, which claims a scoping nobody can check"
            )
        return v

    completeness: Literal["complete", "truncated", "unknown"] = "unknown"
    """Does `instances` hold the WHOLE population the provider knows of, or a prefix of it?

    Mirrors `scoped_by` exactly, one state per read:

        "complete"    the provider claims `instances` IS the whole population
        "truncated"   the provider claims more exist beyond what `instances` holds
        "unknown"     the provider has not said either way

    DEFAULTS TO `"unknown"`, AND THE DEFAULT IS THE FAIL-SAFE DIRECTION, for the identical reason
    `scoped_by` defaults to `[]` rather than to something read as "definitely scoped". 0 of 5
    providers in the module docstring's table currently emit this field, so a provider that has
    not been migrated must not be read as either "complete" or "truncated" — `"unknown"` is an
    honest under-claim, never a guess that collapses into `"complete"`. A caller MUST be able to
    tell "the provider said complete" from "the provider never said anything about completeness";
    that distinction is the entire reason this is a three-value `Literal` and not a boolean.

    THIS FIELD IS A CLAIM THE PROVIDER MAKES, NEVER SOMETHING THIS MODULE DERIVES. Inferring
    `completeness` from `len(instances) < limit` would look free — a response with fewer than
    `limit` instances often IS complete — but a provider that has 3 of 25 requested and forgot to
    declare `limit` is not "complete" just because it returned fewer than the limit. That is
    exactly the shape this docstring warns against for `scoped_by` in the other direction: a claim
    this module invents is as dishonest as a claim a provider drops.
    """

    total_available: Optional[int] = None
    """The size of the population the provider knows about, WHEN it knows it.

    `None` means "not knowable or not reported", not zero — a provider that cannot count its own
    population (or has not been migrated to say so) must not be read as reporting an empty one.
    Paired with `completeness == "truncated"`, this is how far short `instances` falls; paired
    with `"unknown"`, it may still be `None`, because a provider can fail to claim completeness
    and fail to know its population size independently of each other.
    """

    def is_class_wide(self) -> bool:
        """True when nothing was scoped. The ask builder refuses a scoped menu on this."""
        return len(self.scoped_by) == 0

    def honoured(self, slot: str) -> bool:
        """Did the provider apply THIS slot? The question the ask builder actually has."""
        return slot in self.scoped_by

    def unhonoured(self, requested: Optional[dict] = None) -> list:
        """Slots that were offered as context and NOT applied — the gap, named.

        A provider honouring one of two slots is neither scoped nor class-wide in the way a
        caller cares about, and this is the only method that surfaces the difference.
        """
        return sorted(set((requested or {}).keys()) - set(self.scoped_by))


def unhonoured_scoping(
    declared: Sequence[str],
    bound: Mapping[str, str],
    response: "EnumerateInstancesResponse",
) -> list:
    """Declared narrowing slots that were BOUND this turn and the provider did NOT apply.

    The invariant `scoped_by <= narrowed_by & bound`, evaluated: this returns what is missing
    from the left of it. Non-empty means the menu is a class-wide list wearing a scoped one —
    draw it and the user picks an option the verb will reject. Empty means the menu is honest,
    either because everything declared was applied or because nothing declared is bound yet.

    **INTERSECTING WITH `bound` IS THE WHOLE POINT.** A slot declared as narrowing but not yet
    bound cannot scope anything, and refusing on it would refuse the first menu of every turn —
    the same over-refusal as treating every bound value as a scoping dimension, reached from
    the other side.

    Takes the declaration as a plain sequence rather than a `SlotDecl`, so `enumeration` does
    not import `graph_manifest`: the gateway already holds the slot, and the contract here is
    the NAMES, not the model.
    """
    return sorted((set(declared) & set(bound)) - set(response.scoped_by))


def over_limit(
    request: "EnumerateInstancesRequest",
    response: "EnumerateInstancesResponse",
) -> bool:
    """Does this answer VIOLATE the invariant `len(instances) <= limit`?

    Unlike `completeness`, which is a claim the provider makes about itself, this is the one
    thing about limit-honouring this module CAN check without trusting anybody: `request.limit`
    is what was asked, `response.instances` is what came back, and nothing before this function
    compared the two. A provider that ignores `limit` entirely — the two providers in the module
    docstring's table that enumerate unbounded — would otherwise pass silently, its answer
    accepted as a menu with no seal on its size at all.

    A free function taking BOTH objects, not a method on either, for the same reason as
    `unhonoured_scoping`: the request and the response are both needed, and neither one alone
    carries enough information — a response cannot know what was asked, and a request cannot
    know what came back.
    """
    return len(response.instances) > request.limit
