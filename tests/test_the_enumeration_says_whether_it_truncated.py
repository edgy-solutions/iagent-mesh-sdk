"""An enumeration must say whether the menu it drew is the whole population.

THE DEFECT THE SHAPE PREVENTS: a truncated list wearing a complete menu is the same defect as a
class-wide list wearing a scoped one (see `test_the_enumeration_says_what_scoped_it.py`) — the
caller cannot tell "these are the options" from "these are the first 25 of them", and a menu that
silently omits the user's answer is worse than a refusal.

Three states, mirroring `scoped_by` exactly: complete (`completeness == "complete"`), truncated
(`completeness == "truncated"`), and unknown — the provider never said (`completeness ==
"unknown"`, the default). Plus the one invariant this module can check without trusting anybody's
claim: `len(instances) <= limit`, sealed by `over_limit`.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.enumeration import (
    EnumerateInstancesRequest,
    EnumerateInstancesResponse,
    InstanceOption,
    over_limit,
)

_OPT = [InstanceOption(uri="cost#lot-3", label="Lot 3")]


# ── the three states ─────────────────────────────────────────────────────────────────────

def test_COMPLETENESS_DEFAULTS_TO_UNKNOWN_AND_THAT_IS_THE_FAIL_SAFE_DIRECTION():
    """THE ARM THAT MATTERS. A provider that has not been migrated to this field must read as
    UNKNOWN, not as "complete" and not as "truncated" — either of those would be a claim nobody
    made. The opposite default (defaulting to "complete") would let every unmigrated provider's
    answer, truncated or not, be read as the whole population, which is the exact defect."""
    r = EnumerateInstancesResponse(instances=_OPT)
    assert r.completeness == "unknown", (
        "an omitted completeness must not collapse into either claimed state — it is honest "
        "under-claim, exactly mirroring why scoped_by defaults to []"
    )


def test_COMPLETE_AND_TRUNCATED_BOTH_ROUND_TRIP_AS_EXPLICIT_CLAIMS():
    complete = EnumerateInstancesResponse(instances=_OPT, completeness="complete")
    truncated = EnumerateInstancesResponse(instances=_OPT, completeness="truncated")
    assert complete.completeness == "complete"
    assert truncated.completeness == "truncated"
    assert complete.completeness != truncated.completeness != "unknown"


def test_AN_INVALID_COMPLETENESS_VALUE_IS_REFUSED():
    """`Literal` constrains the value set, but this repo asserts behaviour rather than trusting a
    library silently — the same convention `_no_blank_slot_names` follows for `scoped_by`."""
    with pytest.raises(ValidationError):
        EnumerateInstancesResponse(instances=_OPT, completeness="partial")


def test_TOTAL_AVAILABLE_DEFAULTS_TO_NONE_AND_ROUND_TRIPS():
    """`None` means "not knowable or not reported", not zero — a provider that cannot count its
    own population must not be read as reporting an empty one."""
    r = EnumerateInstancesResponse(instances=_OPT)
    assert r.total_available is None

    known = EnumerateInstancesResponse(
        instances=_OPT, completeness="truncated", total_available=12
    )
    assert known.total_available == 12


def test_COMPLETENESS_IS_A_CLAIM_NOT_A_DERIVED_COUNT():
    """THE SINGLE MOST IMPORTANT TEST. A provider with 3 of 25 requested that forgot to declare
    limit is not "complete" just because it returned fewer than the limit. Nothing in this model
    may infer completeness from `len(instances) < limit` — that inference is exactly the shape
    this module's docstring warns against for `scoped_by`, in the other direction: a claim this
    module invents is as dishonest as a claim a provider drops."""
    req = EnumerateInstancesRequest(class_uri="cost#RateTable", limit=25)
    resp = EnumerateInstancesResponse(instances=_OPT)  # 1 instance, well under limit=25

    assert len(resp.instances) < req.limit
    assert resp.completeness == "unknown", (
        "fewer instances than the limit must not be read as complete — nothing here derives "
        "completeness from the count"
    )


# ── the seal: len(instances) <= limit ─────────────────────────────────────────────────────

def test_OVER_LIMIT_IS_FALSE_WHEN_THE_INVARIANT_HOLDS():
    req = EnumerateInstancesRequest(class_uri="cost#RateTable", limit=3)
    under = EnumerateInstancesResponse(instances=_OPT)
    assert not over_limit(req, under)


def test_OVER_LIMIT_IS_FALSE_AT_THE_EXACT_EQUALITY_BOUNDARY():
    """`len(instances) == limit` is NOT a violation — the invariant is `<=`, and a boundary bug
    here is exactly the class of defect this repo's tests are written to catch."""
    req = EnumerateInstancesRequest(class_uri="cost#RateTable", limit=1)
    exact = EnumerateInstancesResponse(instances=_OPT)
    assert len(exact.instances) == req.limit
    assert not over_limit(req, exact)


def test_OVER_LIMIT_IS_TRUE_WHEN_THE_PROVIDER_IGNORED_LIMIT():
    """A provider that ignores limit entirely — the two providers in the module docstring's table
    that enumerate unbounded — would otherwise pass silently. This is the seal."""
    req = EnumerateInstancesRequest(class_uri="cost#RateTable", limit=1)
    over = EnumerateInstancesResponse(
        instances=[
            InstanceOption(uri="cost#lot-1", label="Lot 1"),
            InstanceOption(uri="cost#lot-2", label="Lot 2"),
        ]
    )
    assert len(over.instances) > req.limit
    assert over_limit(req, over)
