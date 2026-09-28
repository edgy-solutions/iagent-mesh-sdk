"""`SlotDecl.narrowed_by` — which OTHER slots of a row restrict this slot's valid values.

THE DEFECT IT EXISTS TO PREVENT is a class-wide list wearing a scoped menu: the ask builder
draws every instance of a class, the user picks one, and the verb rejects the pick because a slot
already bound made it invalid. `cost#RateTable` enumerates to 12 while lot 3 accepts 2.

THE DEFECT IT MUST NOT BECOME is the over-refusal that was caught on the gateway half: treating
every bound value as a scoping dimension refuses menus that were always right. `lot` genuinely
restricts which rate vintages are valid; `direction: upstream` restricts nothing, and nothing in
a provider's silence tells them apart. Only the row knows, so the row declares it.

A REFUSAL SUITE WITH NO POSITIVE CONTROL IS THE FAILURE IT TESTS FOR — a model that refused
everything would satisfy every refusal below — so the accepting arms come first, and §4 asserts
the two shapes that must NOT be refused.
"""

from __future__ import annotations

import copy
import inspect

import pytest

from iagent_mesh.enumeration import EnumerateInstancesResponse, unhonoured_scoping
from iagent_mesh.graph_manifest import GraphManifest, SlotDecl, manifest_ref

TWO_SLOTS = {
    "graph_id": "cost_lot_costing_review",
    "module": "graphs.cost_lot_costing_review",
    "verb": "mesh:costLotCostingReview",
    "name": "engine_lg_lot_costing_review",
    "description": "One lot's cost under a rate vintage.",
    "input_uri": "http://invincible-agent/cost#ProductionLot",
    "output_uri": "http://invincible-agent/cost#LotCostingReview",
    "arity": "single",
    "refusal": "fail",
    "slots": [
        {"name": "lot", "kind": "spoken-mandatory", "type": "integer", "required": True,
         "referent": "http://invincible-agent/cost#ProductionLot"},
        {"name": "rate_vintage", "kind": "spoken-mandatory", "type": "string",
         "required": True},
    ],
}


def _row(**slot_over):
    """The real two-slot row, with the SECOND slot perturbed. Two slots is the minimum that can
    express a narrowing at all, which is why this file does not reuse the one-slot VALID."""
    d = copy.deepcopy(TWO_SLOTS)
    d["slots"][1].update(slot_over)
    return d


# -- 1. the positive controls, first --------------------------------------------------------

def test_the_declaration_this_field_exists_for_is_ACCEPTED():
    """POSITIVE CONTROL. `rate_vintage` is narrowed by `lot` — the case from the ruling."""
    m = GraphManifest(**_row(narrowed_by=["lot"]))
    assert m.slots[1].narrowed_by == ["lot"]


def test_a_row_that_declares_NOTHING_is_still_valid():
    """THE SECOND POSITIVE CONTROL, and the one that matters at the pin: every row in the fleet
    today declares no narrowing, and this field's arrival must not invalidate one of them."""
    assert GraphManifest(**_row()).slots[1].narrowed_by is None


# -- 2. every way a declaration could silently never fire -----------------------------------

@pytest.mark.parametrize("over,because", [
    (dict(narrowed_by=["Lot"]), "is not a slot of this row"),
    (dict(narrowed_by=["rate_vintage"]), "cannot be narrowed by itself"),
    (dict(narrowed_by=[" "]), "blank slot name"),
    (dict(narrowed_by=["lot", "lot"]), "repeats a slot name"),
    (dict(narrowed_by=[]), "present but empty"),
    (dict(kind="handle", required=False, narrowed_by=["lot"]), "belongs on a SPOKEN slot"),
])
def test_a_declaration_that_could_never_fire_is_REFUSED_for_its_own_reason(over, because):
    """THE MESSAGE IS ASSERTED, NOT JUST THE RAISE. `_no_untyped_passthrough` and the arity rule
    also refuse rows in this file's shape, so "something raised" would score a refusal from the
    wrong validator as a pass — which is measuring the wrong thing while looking green.

    Each case is a declaration that would be INERT rather than wrong: a name matching no slot
    never appears in any provider's `scoped_by`, so the menu is refused forever and the row looks
    correct. A `handle` carrier is inert because nothing draws a menu for a dispatcher-resolved
    slot. An inert declaration that looks live is the defect this field exists to prevent.
    """
    with pytest.raises(ValueError, match=because):
        GraphManifest(**_row(**over))


# -- 3. the two shapes that must NOT be refused ---------------------------------------------

def test_a_CYCLE_is_legitimate_and_is_accepted():
    """THE PLAUSIBLE WRONG STRICTNESS. Mutual narrowing is not a contradiction: whichever slot is
    bound first scopes the other's menu. Rejecting cycles is the tempting fix and it would outlaw
    a correct row."""
    d = copy.deepcopy(TWO_SLOTS)
    d["slots"][0]["narrowed_by"] = ["rate_vintage"]
    d["slots"][1]["narrowed_by"] = ["lot"]
    m = GraphManifest(**d)
    assert [s.narrowed_by for s in m.slots] == [["rate_vintage"], ["lot"]]


def test_a_slot_may_be_narrowed_BY_a_handle():
    """The restriction is on the CARRIER, not on the names. A handle the dispatcher bound can
    genuinely restrict what a speaker is then offered — only the drawing of a menu is a spoken
    concern, and that is the carrier's side."""
    d = copy.deepcopy(TWO_SLOTS)
    d["slots"].append({"name": "site", "kind": "handle", "type": "string"})
    d["slots"][1]["narrowed_by"] = ["site"]
    assert GraphManifest(**d).slots[1].narrowed_by == ["site"]


# -- 4. the ref consequence, which decided the default ---------------------------------------

def test_declaring_a_narrowing_MINTS_A_NEW_REF_and_not_declaring_one_does_not():
    """BOTH DIRECTIONS, because only the pair justifies `Optional[...] = None`.

    `ref_basis` dumps slots with `exclude_none=True`. A `= []` default would put `narrowed_by:
    []` on every slot of every row and move EVERY manifest ref in the fleet — including rows with
    no menu and no interest in scoping — through the registrar's idempotency key. Measured
    against the real rows before the default was chosen: `fin_program_brief` moved under `= []`
    and did not under `None`.
    """
    unchanged = manifest_ref(GraphManifest(**_row()))
    declared = manifest_ref(GraphManifest(**_row(narrowed_by=["lot"])))
    assert declared != unchanged, (
        "declaring a narrowing did not move the ref — a changed slot must mint a new contract id"
    )
    assert manifest_ref(GraphManifest(**_row())) == unchanged, (
        "a row that declares nothing must hash exactly as it did before the field existed"
    )


# -- 5. the invariant, asserted against the docstrings themselves ----------------------------

INVARIANT = "scoped_by  <=  narrowed_by  &  bound"


def test_BOTH_SIDES_NAME_THE_OTHER_AND_STATE_THE_INVARIANT():
    """RULED 2026-09-19 as the condition on the name, and asserted MECHANICALLY rather than by
    having read them once.

    The two fields are halves of one rule and are different KINDS of statement:
    `SlotDecl.narrowed_by` is an obligation fixed at ratification, `scoped_by` is a provider's
    claim about one answer. A reader landing on either half must be told the other exists, or the
    comparison at the heart of the refusal reads as a tautology. A cross-reference that lives
    only in a session's memory is the kind that rots silently.
    """
    slot_side = inspect.getsource(SlotDecl)
    resp_side = inspect.getsource(EnumerateInstancesResponse)

    assert "EnumerateInstancesResponse" in slot_side and "scoped_by" in slot_side, (
        "SlotDecl.narrowed_by does not name the field it is half of"
    )
    assert "SlotDecl" in resp_side and "narrowed_by" in resp_side, (
        "EnumerateInstancesResponse.scoped_by does not name the field it is half of"
    )
    for side, where in ((slot_side, "SlotDecl"), (resp_side, "EnumerateInstancesResponse")):
        assert INVARIANT in side, f"{where} does not state the invariant {INVARIANT!r}"
    assert "narrowed_by" in (unhonoured_scoping.__doc__ or ""), (
        "the helper that EVALUATES the invariant does not name it"
    )


# -- 6. the helper, including the arm that is the over-refusal from the other side -----------

@pytest.mark.parametrize("declared,bound,scoped_by,expected", [
    (["lot"], {"lot": "3"}, ["lot"], []),
    (["lot"], {"lot": "3"}, [], ["lot"]),
    (["lot"], {}, [], []),
    ([], {"direction": "upstream"}, [], []),
    (["lot", "site"], {"lot": "3", "site": "A"}, ["lot"], ["site"]),
])
def test_unhonoured_scoping_names_what_was_declared_bound_and_NOT_applied(
        declared, bound, scoped_by, expected):
    """Non-empty means refuse: the menu is class-wide wearing a scoped one.

    THE THIRD CASE IS THE ONE TO HOLD ON TO. A slot declared as narrowing but NOT YET BOUND
    cannot scope anything, and refusing on it would refuse the first menu of every turn — the
    same over-refusal as treating every bound value as a scoping dimension, reached from the
    other side. Declaration alone is not grounds to refuse; declaration INTERSECTED WITH BOUND
    is.

    The fourth is the gateway test's own case: `direction` is bound, nothing declares it, and the
    menu is drawn.
    """
    response = EnumerateInstancesResponse(scoped_by=scoped_by)
    assert unhonoured_scoping(declared, bound, response) == expected
