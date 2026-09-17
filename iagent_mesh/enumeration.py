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

── THE THREE STATES OF AN ENUMERATION, AND WHY `scoped_by` IS A FIELD ──────────────────────
RULED 2026-09-16. A provider may be handed bound slots as scoping context; the response must say
whether it USED them.

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

⚠ **THE SAME RULE APPLIES TO `limit` AND IS NOT IMPLEMENTED HERE.** A truncated list wearing a
complete menu is the same defect as a class-wide list wearing a scoped one: the caller cannot
tell "these are the options" from "these are the first 25 of them", and a menu that silently
omits the user's answer is worse than a refusal. The ruling covered scoping, so this model covers
scoping — the symmetry is recorded rather than invented, and it wants its own ruling.

── WHAT THIS MODULE DOES NOT DO ────────────────────────────────────────────────────────────
It does not make anything call an enumerate. `src/iagent/defs/dynamic_supervisor.py` records that
Engine P is a REGISTERED provider with no router-side fan-out — "a registration is not a reachable
call" — so the disposition runs with no enumerator and reports `free_text_reason: no_provider`.
Binding this shape is the contract half; the fan-out is a separate act by a separate lane.
"""
from __future__ import annotations

from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "DEFAULT_ENUMERATE_LIMIT",
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
    """

    @field_validator("scoped_by")
    @classmethod
    def _no_blank_slot_names(cls, v: Sequence[str]) -> Sequence[str]:
        if any(not s or not s.strip() for s in v):
            raise ValueError(
                "scoped_by carries a blank slot name, which claims a scoping nobody can check"
            )
        return v

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
