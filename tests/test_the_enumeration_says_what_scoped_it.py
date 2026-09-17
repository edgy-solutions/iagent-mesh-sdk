"""An enumeration must say whether it used the context it was given.

THE DEFECT THE SHAPE PREVENTS: `cost#RateTable` enumerates to 12 while lot 3 accepts 2. A
class-wide list drawn as a lot-scoped menu offers ten options that produce the refusal the menu
exists to prevent — the user picks and the pick is rejected. So the answer carries what scoped
it, and the ask builder refuses to draw a scoped menu from a class-wide list.

Three states: scoped (`scoped_by` non-empty), class-wide (`scoped_by == []`), and no enumeration
at all (no response — no provider, or a refusal).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.enumeration import (
    DEFAULT_ENUMERATE_LIMIT,
    EnumerateInstancesRequest,
    EnumerateInstancesResponse,
    InstanceOption,
)

_OPT = [InstanceOption(uri="cost#lot-3", label="Lot 3")]


# ── the three states ─────────────────────────────────────────────────────────────────────

def test_A_SCOPED_ANSWER_NAMES_THE_SLOTS_IT_APPLIED():
    r = EnumerateInstancesResponse(instances=_OPT, scoped_by=["lot"])
    assert not r.is_class_wide()
    assert r.honoured("lot")


def test_A_CLASS_WIDE_ANSWER_IS_THE_DEFAULT_AND_THE_FAIL_SAFE_DIRECTION():
    """THE ARM THAT MATTERS. A provider that honours the slots but FORGETS the field must read as
    class-wide, so the menu is refused — it under-claims. The opposite default would make a
    forgetful provider's class-wide list look scoped, which is the exact defect."""
    r = EnumerateInstancesResponse(instances=_OPT)
    assert r.is_class_wide(), (
        "an omitted scoped_by does not read as class-wide, so a forgetful provider's class-wide "
        "list would be drawn as a scoped menu"
    )
    assert not r.honoured("lot")


def test_SCOPED_BY_NAMES_SLOTS_RATHER_THAN_BEING_A_BOOLEAN():
    """A provider handed two slots that honours ONE has scoped by one of two. A boolean would let
    the ask builder believe both were applied, which is the same over-claim in miniature."""
    requested = {"lot": "3", "category": "LABOUR"}
    r = EnumerateInstancesResponse(instances=_OPT, scoped_by=["lot"])
    assert r.honoured("lot") and not r.honoured("category")
    assert r.unhonoured(requested) == ["category"], (
        "the partially-honoured case is invisible — neither scoped nor class-wide is the whole "
        "truth, and only the gap names it"
    )


def test_A_BLANK_SLOT_NAME_IS_REFUSED():
    """`scoped_by: [""]` claims a scoping nobody can check — non-empty, so it reads as scoped,
    while naming no slot the ask builder can verify against what it sent."""
    with pytest.raises(ValidationError):
        EnumerateInstancesResponse(instances=_OPT, scoped_by=[""])


# ── the request: the divergences this shape resolves ─────────────────────────────────────

def test_AN_EMPTY_CLASS_URI_IS_REFUSED():
    """planning_agent declared `class_uri: str = ''`, so the same malformed request was a refusal
    from four providers and an answer from one. An enumeration with no class has nothing to
    enumerate."""
    with pytest.raises(ValidationError):
        EnumerateInstancesRequest(class_uri="")
    with pytest.raises(ValidationError):
        EnumerateInstancesRequest(class_uri="   ")


def test_CLASS_URI_IS_REQUIRED_NOT_DEFAULTED():
    with pytest.raises(ValidationError):
        EnumerateInstancesRequest()


def test_THERE_IS_EXACTLY_ONE_LIMIT_DEFAULT():
    """THE DIVERGENCE WITH THE WIDEST BLAST RADIUS: the menu's SIZE depended on who answered —
    25 from cost and safety, 8 from finance, unbounded from ontology and planning. The ask
    builder draws without knowing which it got, so 'the options' was a different set per provider
    for the same question."""
    assert EnumerateInstancesRequest(class_uri="x#C").limit == DEFAULT_ENUMERATE_LIMIT


def test_A_LIMIT_BELOW_ONE_IS_REFUSED():
    with pytest.raises(ValidationError):
        EnumerateInstancesRequest(class_uri="x#C", limit=0)


def test_AN_UNKNOWN_FIELD_IS_REFUSED_RATHER_THAN_IGNORED():
    """THE ROOT OF THE WHOLE DIVERGENCE. A provider that silently ignores a field it does not
    understand is how `limit` came to mean three things — the caller sent it, one engine honoured
    it, and nothing said so. A rejected unknown field is a fixable error; an ignored one is a
    wrong answer."""
    with pytest.raises(ValidationError):
        EnumerateInstancesRequest(class_uri="x#C", lmit=5)
    with pytest.raises(ValidationError):
        EnumerateInstancesResponse(instances=_OPT, scoped=True)


def test_BOUND_SLOTS_ARE_CONTEXT_NOT_A_DEMAND():
    """Passing context must not be a requirement to honour it — a provider that cannot scope
    answers class-wide and says so. So a request carrying slots is valid on its own, and nothing
    here forces a scoped response."""
    req = EnumerateInstancesRequest(class_uri="cost#RateTable", bound_slots={"lot": "3"})
    assert req.bound_slots == {"lot": "3"}
    ignored = EnumerateInstancesResponse(instances=_OPT)
    assert ignored.is_class_wide()
    assert ignored.unhonoured(req.bound_slots) == ["lot"]


def test_THE_SHAPE_IS_REACHABLE_FROM_THE_PACKAGE_ROOT():
    """Five engines transcribed this model because there was nothing to bind. A shared shape that
    consumers cannot find is the sixth transcription waiting to happen."""
    import iagent_mesh

    for n in ("EnumerateInstancesRequest", "EnumerateInstancesResponse", "InstanceOption"):
        assert hasattr(iagent_mesh, n), f"{n} is not reachable from `import iagent_mesh`"
        assert n in iagent_mesh.__all__
